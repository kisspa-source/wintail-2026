"""필터 매칭 + 백그라운드 hide 스캔.

Matcher: 부분문자열/정규식(대소문자 옵션)을 캡슐화한다. 하이라이트 모드(UI)는
가시 영역 텍스트에 matches_text/find_spans를 쓰고, hide 모드는 FilterScanner가
전체를 스캔해 매칭 라인 번호를 누적한다.

FilterScanner는 백그라운드 스레드에서 동작하며 매칭 라인 번호를 array('q')에
스트리밍으로 쌓는다. 부분문자열 + 대소문자 구분 + 단일바이트 인코딩이면 디코드
없이 raw 바이트에서 바로 탐색(고속). 그 외에는 줄을 디코드해 매칭한다.
매칭이 과밀하면 dense_cap에서 누적을 멈춰 메모리를 보호한다.
"""

from __future__ import annotations

import re
import threading
from array import array
from bisect import bisect_right
from collections.abc import Callable

from engine.events import FilterComplete, FilterProgress
from engine.filereader import FileReader
from engine.linescan import iter_lines

DENSE_CAP = 2_000_000
PROGRESS_BYTES = 16 << 20


class Matcher:
    def __init__(self, pattern: str, *, regex: bool = False, ignore_case: bool = False):
        self.pattern = pattern
        self.regex = regex
        self.ignore_case = ignore_case
        self.valid = True
        self._re: re.Pattern | None = None
        self._needle_lower = pattern.lower() if ignore_case else pattern
        if regex and pattern:
            try:
                self._re = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
            except re.error:
                self.valid = False

    @property
    def is_plain_substring(self) -> bool:
        return bool(self.pattern) and not self.regex and not self.ignore_case

    def matches_text(self, text: str) -> bool:
        if not self.pattern or not self.valid:
            return False
        if self.regex:
            return self._re.search(text) is not None
        if self.ignore_case:
            return self._needle_lower in text.lower()
        return self.pattern in text

    def find_spans(self, text: str) -> list[tuple[int, int]]:
        if not self.pattern or not self.valid:
            return []
        if self.regex:
            return [(m.start(), m.end()) for m in self._re.finditer(text) if m.end() > m.start()]
        spans = []
        hay = text.lower() if self.ignore_case else text
        needle = self._needle_lower if self.ignore_case else self.pattern
        start = 0
        nlen = len(needle)
        while True:
            i = hay.find(needle, start)
            if i == -1:
                break
            spans.append((i, i + nlen))
            start = i + nlen
        return spans


class FilterScanner:
    def __init__(
        self,
        reader: FileReader,
        emit: Callable[[object], None],
        matcher: Matcher,
        *,
        start_offset: int = 0,
        read_chunk: int,
        line_cap: int,
        total_size: int,
        stop_event: threading.Event | None = None,
        dense_cap: int = DENSE_CAP,
        progress_bytes: int = PROGRESS_BYTES,
    ):
        self.reader = reader
        self.emit = emit
        self.matcher = matcher
        self.start_offset = start_offset
        self.read_chunk = read_chunk
        self.line_cap = line_cap
        self.total_size = total_size
        self.stop_event = stop_event
        self.dense_cap = dense_cap
        self.progress_bytes = progress_bytes
        self.matches = array("q")  # 매칭 라인 번호
        self.offsets = array("q")  # 각 매칭 라인의 시작 바이트 오프셋
        self.capped = False
        self._lock = threading.Lock()

    def matched_count(self) -> int:
        with self._lock:
            return len(self.matches)

    def match_at(self, row: int) -> int | None:
        with self._lock:
            if 0 <= row < len(self.matches):
                return self.matches[row]
            return None

    def rank_of(self, line_no: int) -> int:
        """line_no 이하인 일치 줄의 개수(= 그 줄의 1-based 순위). 매칭은 줄 순서대로
        쌓이므로 matches는 오름차순이라 이분 탐색."""
        with self._lock:
            return bisect_right(self.matches, line_no)

    def offset_at(self, row: int) -> int | None:
        with self._lock:
            if 0 <= row < len(self.offsets):
                return self.offsets[row]
            return None

    def _stopped(self) -> bool:
        return self.stop_event is not None and self.stop_event.is_set()

    def _flush(self, lines: list[int], offs: list[int]) -> None:
        if lines:
            with self._lock:
                self.matches.extend(lines)
                self.offsets.extend(offs)
            lines.clear()
            offs.clear()

    def run(self) -> None:
        matcher = self.matcher
        plain = matcher.is_plain_substring and self.reader.info.unit_size == 1
        if plain:
            count = self._scan_fast(matcher.pattern.encode(self.reader.info.codec, errors="ignore"))
        else:
            count = self._scan_generic()
        if count is not None:
            self.emit(FilterComplete(count))

    def _scan_generic(self) -> int | None:
        """정규식/대소문자무시/UTF-16 등 — 줄을 디코드해 매칭(느린 일반 경로)."""
        reader = self.reader
        matcher = self.matcher
        batch_lines: list[int] = []
        batch_offs: list[int] = []
        count = 0
        last_progress = self.start_offset
        for line_no, off, raw in iter_lines(
            reader, self.start_offset, 0,
            read_chunk=self.read_chunk, line_cap=self.line_cap,
        ):
            if self._stopped():
                self._flush(batch_lines, batch_offs)
                return None
            text, _ = reader.decode_line(raw)
            if matcher.matches_text(text):
                batch_lines.append(line_no)
                batch_offs.append(off)
                count += 1
                if count >= self.dense_cap:
                    self.capped = True
                    self._flush(batch_lines, batch_offs)
                    return count
            if off - last_progress >= self.progress_bytes:
                self._flush(batch_lines, batch_offs)
                self.emit(FilterProgress(count, off, self.total_size))
                last_progress = off
        self._flush(batch_lines, batch_offs)
        return count

    def _scan_fast(self, needle: bytes) -> int | None:
        """부분문자열(대소문자 구분, 단일바이트 인코딩) — 히트 기반 고속 스캔.

        줄마다 Python으로 순회하지 않고, needle 출현 위치(C find)마다 그 줄 번호와
        시작 오프셋을 C 연산(count/rfind)으로 계산한다. 같은 줄의 중복 히트는 합친다.
        """
        reader = self.reader
        keep = max(0, len(needle) - 1)
        batch_lines: list[int] = []
        batch_offs: list[int] = []
        count = 0
        last_progress = self.start_offset

        read_pos = self.start_offset
        carry = b""
        line_no = 0
        cur_line_start = self.start_offset
        last_recorded = -1

        while True:
            if self._stopped():
                self._flush(batch_lines, batch_offs)
                return None
            new = reader.read(read_pos, self.read_chunk)
            data = carry + new
            chunk_abs = read_pos - len(carry)
            read_pos += len(new)
            eof = not new
            boundary = len(data) if eof else len(data) - keep
            if boundary < 0:
                boundary = 0

            p = 0
            while True:
                h = data.find(needle, p)
                if h == -1 or h >= boundary:
                    break
                seg_nl = data.count(b"\n", p, h)
                if seg_nl:
                    line_no += seg_nl
                    last_nl = data.rfind(b"\n", p, h)
                    cur_line_start = chunk_abs + last_nl + 1
                if line_no != last_recorded:
                    batch_lines.append(line_no)
                    batch_offs.append(cur_line_start)
                    last_recorded = line_no
                    count += 1
                    if count >= self.dense_cap:
                        self.capped = True
                        self._flush(batch_lines, batch_offs)
                        return count
                p = h + 1

            # 다음 청크를 위해 경계까지 줄 계정 진행
            tail_nl = data.count(b"\n", p, boundary)
            if tail_nl:
                line_no += tail_nl
                last_nl = data.rfind(b"\n", p, boundary)
                cur_line_start = chunk_abs + last_nl + 1
            carry = data[boundary:]

            if read_pos - last_progress >= self.progress_bytes:
                self._flush(batch_lines, batch_offs)
                self.emit(FilterProgress(count, read_pos, self.total_size))
                last_progress = read_pos

            if eof:
                break

        self._flush(batch_lines, batch_offs)
        return count
