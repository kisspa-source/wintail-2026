"""느린 쿼리 스캔 — 'Time:<ms>' 실행시간이 임계값 이상인 줄을 백그라운드로 수집.

SLF4JQueryLoggingListener류 로그의 `Time:123 [QET:...]` 패턴이 대상이다.
줄을 디코드하기 전에 인코딩된 'Time:' 바이트 존재부터 확인(C find)해서
대부분의 줄을 디코드 없이 건너뛴다. 결과(줄 번호, ms)는 array('q')에
스트리밍으로 쌓이고, FilterScanner처럼 진행/완료 이벤트를 발행한다.
"""

from __future__ import annotations

import re
import threading
from array import array
from collections.abc import Callable

from engine.events import SlowScanComplete, SlowScanProgress
from engine.filereader import FileReader
from engine.linescan import iter_lines

TIME_RE = re.compile(r"\bTime:(\d+)\b")  # \b로 Uptime: 등 접미 일치를 배제
PROGRESS_BYTES = 16 << 20
MAX_HITS = 200_000  # 폭주 방어 — 임계값이 너무 낮으면 여기서 멈추고 capped 표시


def slow_ms(text: str, threshold_ms: int) -> int | None:
    """줄에서 임계값 이상인 Time: 값 중 최댓값(ms). 없으면 None."""
    worst = None
    for m in TIME_RE.finditer(text):
        v = int(m.group(1))
        if v >= threshold_ms and (worst is None or v > worst):
            worst = v
    return worst


class SlowQueryScanner:
    def __init__(
        self,
        reader: FileReader,
        emit: Callable[[object], None],
        threshold_ms: int,
        *,
        start_offset: int = 0,
        read_chunk: int,
        line_cap: int,
        total_size: int,
        stop_event: threading.Event | None = None,
        max_hits: int = MAX_HITS,
        progress_bytes: int = PROGRESS_BYTES,
    ):
        self.reader = reader
        self.emit = emit
        self.threshold_ms = threshold_ms
        self.start_offset = start_offset
        self.read_chunk = read_chunk
        self.line_cap = line_cap
        self.total_size = total_size
        self.stop_event = stop_event
        self.max_hits = max_hits
        self.progress_bytes = progress_bytes
        self.lines = array("q")  # 느린 쿼리 줄 번호(0-base)
        self.times = array("q")  # 각 줄의 실행시간(ms)
        self.capped = False
        self._lock = threading.Lock()

    def hit_count(self) -> int:
        with self._lock:
            return len(self.lines)

    def hit_at(self, i: int) -> tuple[int, int] | None:
        """(줄 번호, ms). 범위 밖이면 None."""
        with self._lock:
            if 0 <= i < len(self.lines):
                return (self.lines[i], self.times[i])
            return None

    def _stopped(self) -> bool:
        return self.stop_event is not None and self.stop_event.is_set()

    def _flush(self, lines: list[int], times: list[int]) -> None:
        if lines:
            with self._lock:
                self.lines.extend(lines)
                self.times.extend(times)
            lines.clear()
            times.clear()

    def run(self) -> None:
        reader = self.reader
        # 디코드 전 바이트 프리필터. utf-16-le/-be 코덱명은 BOM을 붙이지 않는다.
        # (UTF-16에서 비정렬 우연 일치가 나와도 디코드 후 정규식이 거른다.)
        needle = "Time:".encode(reader.info.codec, errors="ignore") or b"Time:"
        batch_l: list[int] = []
        batch_t: list[int] = []
        count = 0
        last_progress = self.start_offset
        for line_no, off, raw in iter_lines(
            reader, self.start_offset, 0,
            read_chunk=self.read_chunk, line_cap=self.line_cap,
        ):
            if self._stopped():
                self._flush(batch_l, batch_t)
                return
            if needle not in raw:
                continue
            text, _ = reader.decode_line(raw)
            ms = slow_ms(text, self.threshold_ms)
            if ms is not None:
                batch_l.append(line_no)
                batch_t.append(ms)
                count += 1
                if count >= self.max_hits:
                    self.capped = True
                    break
            if off - last_progress >= self.progress_bytes:
                self._flush(batch_l, batch_t)
                self.emit(SlowScanProgress(count, off, self.total_size))
                last_progress = off
        self._flush(batch_l, batch_t)
        self.emit(SlowScanComplete(count))
