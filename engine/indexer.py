"""백그라운드 인덱서 + 공유 스캔 루틴.

scan_forward는 파일의 현재 위치(state.pos)부터 EOF까지 청크로 순차 스캔하며:
  - 개행 수를 C레벨 count로 누적해 total_lines를 갱신하고
  - checkpoint_bytes 간격마다 마지막 라인 시작에 체크포인트를 둔다
모든 줄을 Python으로 순회하지 않아 5GB도 빠르고, 체크포인트 간격이 forward scan
범위를 제한한다.

ScanState는 스캔 진행 상태를 들고 다녀, 초기 인덱싱(BackgroundIndexer)과 이후
실시간 추가분(TailWatcher)이 같은 상태를 이어서 확장할 수 있게 한다.

run()은 스레드 타겟이지만 동기로도 호출 가능해 결정적 테스트가 쉽다.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from engine.events import IndexComplete, IndexProgress
from engine.fileindex import FileIndex
from engine.filereader import FileReader

READ_CHUNK = 1 << 20  # 1 MiB
CHECKPOINT_BYTES = 1 << 20  # 1 MiB
PROGRESS_BYTES = 16 << 20  # 16 MiB마다 진행 이벤트


@dataclass
class ScanState:
    pos: int
    newline_count: int
    last_line_start: int
    last_cp_offset: int

    @classmethod
    def at_start(cls, start_offset: int) -> "ScanState":
        return cls(
            pos=start_offset,
            newline_count=0,
            last_line_start=start_offset,
            last_cp_offset=start_offset,
        )

    def reset(self, start_offset: int) -> None:
        self.pos = start_offset
        self.newline_count = 0
        self.last_line_start = start_offset
        self.last_cp_offset = start_offset


def scan_forward(
    reader: FileReader,
    index: FileIndex,
    state: ScanState,
    *,
    read_chunk: int = READ_CHUNK,
    checkpoint_bytes: int = CHECKPOINT_BYTES,
    stop_event: threading.Event | None = None,
    on_chunk: Callable[[int, int], None] | None = None,
) -> bool:
    """state.pos부터 현재 EOF까지 스캔하며 index/state를 갱신한다.

    EOF에 도달하면 True, stop_event로 중단되면 False를 반환한다.
    """
    nlen = len(reader.info.newline)
    while not (stop_event is not None and stop_event.is_set()):
        data = reader.read(state.pos, read_chunk)
        if not data:
            return True
        k = reader.count_newlines(data)
        if k:
            last_nl = reader.last_newline(data)
            new_last_line_start = state.pos + last_nl + nlen
            if (new_last_line_start - state.last_cp_offset) >= checkpoint_bytes:
                index.add_checkpoint(state.newline_count + k, new_last_line_start)
                state.last_cp_offset = new_last_line_start
            state.newline_count += k
            state.last_line_start = new_last_line_start
        state.pos += len(data)
        total = state.newline_count + (1 if state.pos > state.last_line_start else 0)
        index.update(total, state.pos)
        if on_chunk is not None:
            on_chunk(total, state.pos)
    return False


class BackgroundIndexer:
    def __init__(
        self,
        reader: FileReader,
        index: FileIndex,
        emit: Callable[[object], None],
        *,
        start_offset: int = 0,
        state: ScanState | None = None,
        stop_event: threading.Event | None = None,
        scan_lock: threading.Lock | None = None,
        read_chunk: int = READ_CHUNK,
        checkpoint_bytes: int = CHECKPOINT_BYTES,
        progress_bytes: int = PROGRESS_BYTES,
    ):
        self.reader = reader
        self.index = index
        self.emit = emit
        self.start_offset = start_offset
        self.state = state if state is not None else ScanState.at_start(start_offset)
        self.stop_event = stop_event
        self.scan_lock = scan_lock
        self.read_chunk = read_chunk
        self.checkpoint_bytes = checkpoint_bytes
        self.progress_bytes = progress_bytes

    def run(self) -> None:
        last_emit = self.start_offset

        def on_chunk(total: int, pos: int) -> None:
            nonlocal last_emit
            if pos - last_emit >= self.progress_bytes:
                self.emit(IndexProgress(total, pos, self.reader.size()))
                last_emit = pos

        if self.scan_lock is not None:
            self.scan_lock.acquire()
        try:
            reached_eof = scan_forward(
                self.reader,
                self.index,
                self.state,
                read_chunk=self.read_chunk,
                checkpoint_bytes=self.checkpoint_bytes,
                stop_event=self.stop_event,
                on_chunk=on_chunk,
            )
        finally:
            if self.scan_lock is not None:
                self.scan_lock.release()

        if not reached_eof:
            return  # 취소됨

        self.index.mark_complete()
        self.emit(IndexComplete(self.index.total_lines, self.state.pos))
