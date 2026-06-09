"""실시간 추적(tail -f) + 로그 로테이션 감지 — 외부 의존성 0.

표준 라이브러리만으로 os.stat를 주기적으로 폴링한다:
  - size 증가  → 증가분만 스캔해 인덱스 확장, Appended
  - size 감소  → in-place 트렁케이션 → 인덱스 리셋 후 재스캔, Truncated
  - ino/dev 변경 → 파일 로테이션 → on_reopen 콜백(없으면 트렁케이션처럼 처리)

poll_once()가 한 번의 폴링 단위라 테스트가 결정적이다. run()은 poll_once를
poll_interval 간격으로 반복하는 스레드 루프다.
"""

from __future__ import annotations

import contextlib
import os
import threading
import time
from collections.abc import Callable

from engine.events import Appended, FileError, Truncated
from engine.fileindex import FileIndex
from engine.filereader import FileReader
from engine.indexer import CHECKPOINT_BYTES, READ_CHUNK, ScanState, scan_forward

POLL_INTERVAL = 0.25  # 250 ms


class TailWatcher:
    def __init__(
        self,
        path: str,
        reader: FileReader,
        index: FileIndex,
        state: ScanState,
        emit: Callable[[object], None],
        *,
        scan_lock: threading.Lock | None = None,
        stop_event: threading.Event | None = None,
        poll_interval: float = POLL_INTERVAL,
        read_chunk: int = READ_CHUNK,
        checkpoint_bytes: int = CHECKPOINT_BYTES,
        on_reopen: Callable[[], None] | None = None,
    ):
        self.path = path
        self.reader = reader
        self.index = index
        self.state = state
        self.emit = emit
        self.scan_lock = scan_lock
        self.stop_event = stop_event
        self.poll_interval = poll_interval
        self.read_chunk = read_chunk
        self.checkpoint_bytes = checkpoint_bytes
        self.on_reopen = on_reopen
        self._last: tuple[int, int, int] | None = None

    # ---- 폴링 ----------------------------------------------------------

    def prime(self) -> None:
        """현재 파일 상태를 기준점으로 잡는다(추적 시작 시 1회)."""
        self._last = self._stat()

    def _stat(self) -> tuple[int, int, int] | None:
        try:
            st = os.stat(self.path)
            return (st.st_size, st.st_ino, st.st_dev)
        except OSError:
            return None

    def poll_once(self) -> str:
        cur = self._stat()
        if cur is None:
            self.emit(FileError(f"파일 접근 불가: {self.path}"))
            return "error"
        if self._last is None:
            self._last = cur
            return "init"

        size, ino, dev = cur
        lsize, lino, ldev = self._last
        if (ino, dev) != (lino, ldev):
            result = self._rotate()
        elif size < lsize:
            result = self._truncate()
        elif size > lsize:
            result = self._grow()
        else:
            result = "unchanged"

        self._last = self._stat() or cur
        return result

    def run(self) -> None:
        if self._last is None:
            self.prime()
        while not self._stopped():
            time.sleep(self.poll_interval)
            if self._stopped():
                break
            self.poll_once()

    # ---- 반응 ----------------------------------------------------------

    def _scan(self) -> None:
        lock = self.scan_lock if self.scan_lock is not None else contextlib.nullcontext()
        with lock:
            scan_forward(
                self.reader,
                self.index,
                self.state,
                read_chunk=self.read_chunk,
                checkpoint_bytes=self.checkpoint_bytes,
                stop_event=self.stop_event,
            )

    def _grow(self) -> str:
        self._scan()
        self.emit(Appended(self.index.total_lines, self.reader.size()))
        return "appended"

    def _truncate(self) -> str:
        start = self.reader.info.bom_len
        self.index.reset(start_offset=start)
        self.state.reset(start)
        self._scan()
        self.emit(Truncated(self.reader.size()))
        return "truncated"

    def _rotate(self) -> str:
        if self.on_reopen is not None:
            self.on_reopen()
            return "rotated"
        # 콜백이 없으면 트렁케이션과 동일하게 처음부터 재스캔
        return self._truncate()

    def _stopped(self) -> bool:
        return self.stop_event is not None and self.stop_event.is_set()
