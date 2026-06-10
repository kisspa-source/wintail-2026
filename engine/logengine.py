"""LogEngine — UI가 import하는 유일한 파사드.

reader/index/indexer(이후 tail/filter)를 소유하고, 임의 라인 접근(get_lines),
끝부분(get_tail), 상태 질의, 이벤트 큐를 제공한다. 모든 무거운 작업은
백그라운드 스레드에서 일어나고 결과는 이벤트 큐로 전달된다.
"""

from __future__ import annotations

import queue
import threading

from engine.encoding import detect, info_for_codec
from engine.events import EncodingDetected, Line, Opened
from engine.fileindex import FileIndex
from engine.filereader import DEFAULT_MAX_LINE_BYTES, FileReader
from engine.filterscanner import FilterScanner, Matcher
from engine.indexer import CHECKPOINT_BYTES, READ_CHUNK, BackgroundIndexer, ScanState
from engine.linescan import iter_lines
from engine.slowscan import SlowQueryScanner
from engine.tailwatcher import POLL_INTERVAL, TailWatcher

SAMPLE_BYTES = 65536
MATCH_SCAN_CHUNK = 4000  # next_match_line이 한 번에 읽어 검사하는 줄 수


class LogEngine:
    def __init__(
        self,
        *,
        read_chunk: int = READ_CHUNK,
        checkpoint_bytes: int = CHECKPOINT_BYTES,
        max_line_bytes: int = DEFAULT_MAX_LINE_BYTES,
        poll_interval: float = POLL_INTERVAL,
    ):
        self._events: queue.Queue = queue.Queue()
        self._reader: FileReader | None = None
        self._index: FileIndex | None = None
        self._indexer: BackgroundIndexer | None = None
        self._thread: threading.Thread | None = None
        self._stop: threading.Event | None = None
        self._path: str | None = None
        self._state: ScanState | None = None
        self._scan_lock = threading.Lock()
        self._tail: TailWatcher | None = None
        self._tail_thread: threading.Thread | None = None
        self._tail_stop: threading.Event | None = None
        self._follow = False
        self._matcher: Matcher | None = None
        self._filter_mode: str | None = None
        self._filter_scanner: FilterScanner | None = None
        self._filter_thread: threading.Thread | None = None
        self._filter_stop: threading.Event | None = None
        self._slow_scanner: SlowQueryScanner | None = None
        self._slow_thread: threading.Thread | None = None
        self._slow_stop: threading.Event | None = None
        self.read_chunk = read_chunk
        self.checkpoint_bytes = checkpoint_bytes
        self.max_line_bytes = max_line_bytes
        self.poll_interval = poll_interval
        self._line_cap = max(read_chunk * 2, max_line_bytes * 2)

    # ---- 생애주기 ------------------------------------------------------

    def open(self, path: str, *, encoding: str | None = None, follow: bool = False) -> None:
        self.close()
        with open(path, "rb") as f:
            sample = f.read(SAMPLE_BYTES)
        info = info_for_codec(encoding, sample) if encoding else detect(sample)
        self._reader = FileReader(path, info, max_line_bytes=self.max_line_bytes)
        self._index = FileIndex(start_offset=info.bom_len)
        self._path = path
        self._state = ScanState.at_start(info.bom_len)
        self._emit(Opened(path, self._reader.size(), info.codec))
        self._emit(EncodingDetected(info.codec, info.label))
        self._stop = threading.Event()
        self._indexer = BackgroundIndexer(
            self._reader,
            self._index,
            self._emit,
            start_offset=info.bom_len,
            state=self._state,
            stop_event=self._stop,
            scan_lock=self._scan_lock,
            read_chunk=self.read_chunk,
            checkpoint_bytes=self.checkpoint_bytes,
        )
        self._thread = threading.Thread(
            target=self._indexer.run, name="wintail-indexer", daemon=True
        )
        self._thread.start()
        if follow:
            self.set_follow(True)

    def reopen(self, *, encoding: str | None = None) -> None:
        """같은 파일을 (다른 인코딩으로) 다시 연다. 라인 경계가 인코딩 의존이므로
        전체 재오픈이 필요하다."""
        path = self._path
        follow = self._follow
        if path is None:
            return
        self.open(path, encoding=encoding, follow=follow)

    def close(self) -> None:
        self.set_follow(False)
        self.clear_filter()
        self.stop_slow_scan()
        if self._stop is not None:
            self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._reader is not None:
            self._reader.close()
            self._reader = None
        self._index = None
        self._indexer = None
        self._stop = None
        self._state = None
        self._path = None

    def set_follow(self, enabled: bool) -> None:
        if enabled:
            if self._tail_thread is not None or self._reader is None:
                return
            self._tail_stop = threading.Event()
            self._tail = TailWatcher(
                self._path,
                self._reader,
                self._index,
                self._state,
                self._emit,
                scan_lock=self._scan_lock,
                stop_event=self._tail_stop,
                poll_interval=self.poll_interval,
                read_chunk=self.read_chunk,
                checkpoint_bytes=self.checkpoint_bytes,
            )
            self._tail.prime()
            self._tail_thread = threading.Thread(
                target=self._tail.run, name="wintail-tail", daemon=True
            )
            self._tail_thread.start()
            self._follow = True
        else:
            if self._tail_stop is not None:
                self._tail_stop.set()
            if self._tail_thread is not None:
                self._tail_thread.join(timeout=2.0)
                self._tail_thread = None
            self._tail = None
            self._tail_stop = None
            self._follow = False

    def is_following(self) -> bool:
        return self._follow

    # ---- 필터 ----------------------------------------------------------

    def set_filter(
        self,
        pattern: str,
        *,
        mode: str = "highlight",
        regex: bool = False,
        ignore_case: bool = False,
    ) -> None:
        self.clear_filter()
        if not pattern:
            return
        self._matcher = Matcher(pattern, regex=regex, ignore_case=ignore_case)
        self._filter_mode = mode
        if mode == "hide":
            self.start_match_scan()

    def start_match_scan(self) -> None:
        """현재 매처로 전체 매칭 줄 인덱스를 백그라운드에서 만든다(개수/순위/숨김용).

        hide 모드는 set_filter에서 즉시 호출되고, highlight 모드는 'Enter 찾기'를 처음
        쓸 때 LogTab이 호출한다(그냥 하이라이트만 하면 스캔 비용을 치르지 않음).
        이미 스캐너가 있거나 매처가 없으면 아무 것도 안 한다."""
        m = self._matcher
        if self._filter_scanner is not None or self._reader is None:
            return
        if m is None or not m.valid or not m.pattern:
            return
        self._filter_stop = threading.Event()
        self._filter_scanner = FilterScanner(
            self._reader,
            self._emit,
            m,
            start_offset=self._reader.info.bom_len,
            read_chunk=self.read_chunk,
            line_cap=self._line_cap,
            total_size=self._reader.size(),
            stop_event=self._filter_stop,
        )
        self._filter_thread = threading.Thread(
            target=self._filter_scanner.run, name="wintail-filter", daemon=True
        )
        self._filter_thread.start()

    def match_scan_started(self) -> bool:
        return self._filter_scanner is not None

    def match_rank(self, line_no: int) -> int:
        """현재 일치 줄(line_no)의 1-based 순위(스캐너 기준). 스캐너 없으면 0."""
        sc = self._filter_scanner
        return sc.rank_of(line_no) if sc is not None else 0

    def match_rank_before(self, line_no: int) -> int:
        """line_no 앞(미만)의 일치 줄 개수 — 화면 지우기로 숨겨진 일치를 셀 때 쓴다."""
        sc = self._filter_scanner
        if sc is None or line_no <= 0:
            return 0
        return sc.rank_of(line_no - 1)

    def clear_filter(self) -> None:
        if self._filter_stop is not None:
            self._filter_stop.set()
        if self._filter_thread is not None:
            self._filter_thread.join(timeout=2.0)
            self._filter_thread = None
        self._filter_scanner = None
        self._filter_stop = None
        self._matcher = None
        self._filter_mode = None

    def filter_mode(self) -> str | None:
        return self._filter_mode

    def get_filtered_total(self) -> int:
        return self._filter_scanner.matched_count() if self._filter_scanner is not None else 0

    def is_filter_complete(self) -> bool:
        sc = self._filter_scanner
        return sc is None or not (self._filter_thread and self._filter_thread.is_alive())

    def get_filtered_lines(self, start_row: int, count: int) -> list[Line]:
        sc = self._filter_scanner
        if sc is None or self._reader is None or count <= 0:
            return []
        out: list[Line] = []
        for row in range(start_row, start_row + count):
            line_no = sc.match_at(row)
            offset = sc.offset_at(row)
            if line_no is None or offset is None:
                break
            out.append(self._read_line_at(offset, line_no))
        return out

    def match_spans(self, text: str) -> list[tuple[int, int]]:
        """하이라이트용: 텍스트 내 매칭 구간들. 필터 미설정 시 빈 목록."""
        return self._matcher.find_spans(text) if self._matcher is not None else []

    def next_match_line(self, start_line: int, forward: bool = True) -> int | None:
        """현재 매처에 맞는 다음(또는 이전) 줄 번호. 끝까지 없으면 None(순환 안 함).

        하이라이트 모드에서 'Enter=다음 일치' 탐색에 쓰인다. 줄을 청크로 읽어
        matches_text로 검사하므로 동기적이다(일치가 매우 드문 초대형 파일은 잠깐 멈출
        수 있음). 매처가 없거나 무효면 None.
        """
        m = self._matcher
        if m is None or not m.valid or not m.pattern:
            return None
        total = self.get_total_lines()
        if total <= 0:
            return None
        if forward:
            line = max(0, start_line)
            while line < total:
                chunk = self.get_lines(line, MATCH_SCAN_CHUNK)
                if not chunk:
                    break
                for ln in chunk:
                    if m.matches_text(ln.text):
                        return ln.line_no
                line += len(chunk)
            return None
        hi = min(start_line + 1, total)
        while hi > 0:
            lo = max(0, hi - MATCH_SCAN_CHUNK)
            chunk = self.get_lines(lo, hi - lo)
            for ln in reversed(chunk):
                if m.matches_text(ln.text):
                    return ln.line_no
            hi = lo
        return None

    # ---- 느린 쿼리 스캔 -------------------------------------------------

    def start_slow_scan(self, threshold_ms: int) -> None:
        """Time:<ms>가 threshold_ms 이상인 줄을 백그라운드로 수집한다.

        이전 스캔은 중단하고 새로 시작한다. 결과는 slow_hit_count/slow_hit로
        읽고, 진행/완료는 SlowScanProgress/SlowScanComplete 이벤트로 알린다.
        """
        self.stop_slow_scan()
        if self._reader is None:
            return
        self._slow_stop = threading.Event()
        self._slow_scanner = SlowQueryScanner(
            self._reader,
            self._emit,
            threshold_ms,
            start_offset=self._reader.info.bom_len,
            read_chunk=self.read_chunk,
            line_cap=self._line_cap,
            total_size=self._reader.size(),
            stop_event=self._slow_stop,
        )
        self._slow_thread = threading.Thread(
            target=self._slow_scanner.run, name="wintail-slowscan", daemon=True
        )
        self._slow_thread.start()

    def stop_slow_scan(self) -> None:
        if self._slow_stop is not None:
            self._slow_stop.set()
        if self._slow_thread is not None:
            self._slow_thread.join(timeout=2.0)
            self._slow_thread = None
        self._slow_scanner = None
        self._slow_stop = None

    def slow_hit_count(self) -> int:
        sc = self._slow_scanner
        return sc.hit_count() if sc is not None else 0

    def slow_hit(self, i: int) -> tuple[int, int] | None:
        """i번째 느린 쿼리 (줄 번호, ms). 스캐너 없음/범위 밖이면 None."""
        sc = self._slow_scanner
        return sc.hit_at(i) if sc is not None else None

    def is_slow_scan_complete(self) -> bool:
        return self._slow_scanner is None or not (
            self._slow_thread and self._slow_thread.is_alive())

    def slow_scan_capped(self) -> bool:
        sc = self._slow_scanner
        return bool(sc is not None and sc.capped)

    def _read_line_at(self, offset: int, line_no: int) -> Line:
        reader = self._reader
        assert reader is not None
        nlen = len(reader.info.newline)
        initial = min(65536, self._line_cap)
        data = reader.read(offset, initial)
        nls = reader.find_newlines(data)
        while not nls and len(data) < self._line_cap:
            more = reader.read(offset + len(data), initial)
            if not more:
                break
            data += more
            nls = reader.find_newlines(data)
        raw = data[: nls[0] + nlen] if nls else data
        text, trunc = reader.decode_line(raw)
        return Line(line_no, text, offset, len(raw), trunc)

    # ---- 상태 ----------------------------------------------------------

    def get_total_lines(self) -> int:
        return self._index.total_lines if self._index is not None else 0

    def is_index_complete(self) -> bool:
        return bool(self._index is not None and self._index.complete)

    def get_size(self) -> int:
        return self._reader.size() if self._reader is not None else 0

    # ---- 라인 접근 -----------------------------------------------------

    def get_lines(self, start_line: int, count: int) -> list[Line]:
        if self._reader is None or self._index is None or count <= 0:
            return []
        total = self.get_total_lines()
        if total == 0 or start_line >= total:
            return []
        if start_line < 0:
            start_line = 0
        cp_line, cp_off = self._index.checkpoint_before(start_line)
        out: list[Line] = []
        for line_no, off, raw in iter_lines(
            self._reader, cp_off, cp_line, read_chunk=self.read_chunk, line_cap=self._line_cap
        ):
            if line_no < start_line:
                continue
            if line_no >= total:
                break
            text, trunc = self._reader.decode_line(raw)
            out.append(Line(line_no, text, off, len(raw), trunc))
            if len(out) >= count:
                break
        return out

    def get_tail(self, count: int) -> list[Line]:
        total = self.get_total_lines()
        if total == 0 or count <= 0:
            return []
        return self.get_lines(max(0, total - count), count)

    def get_tail_probe(self, count: int, probe_bytes: int = 262144) -> list[Line]:
        """인덱싱 완료 전 즉시 표시용: 파일 끝 일부만 읽어 마지막 count줄을 돌려준다.

        라인 번호는 아직 알 수 없어 -1(provisional)로 둔다. byte_off는 정확하다.
        """
        if self._reader is None or count <= 0:
            return []
        reader = self._reader
        nlen = len(reader.info.newline)
        bom = reader.info.bom_len
        size = reader.size()
        if size <= bom:
            return []
        start = max(bom, size - probe_bytes)
        unit = reader.info.unit_size
        if unit > 1:
            misalign = (start - bom) % unit
            if misalign:
                start += unit - misalign
        data = reader.read(start, size - start)
        if start > bom:
            # probe 시작이 라인 중간일 수 있으니 첫 개행 전까지 버린다
            nls = reader.find_newlines(data)
            if nls:
                cut = nls[0] + nlen
                start += cut
                data = data[cut:]
        segs: list[tuple[int, bytes]] = []
        last = 0
        for p in reader.find_newlines(data):
            segs.append((start + last, data[last : p + nlen]))
            last = p + nlen
        if last < len(data):
            segs.append((start + last, data[last:]))
        out: list[Line] = []
        for off, raw in segs[-count:]:
            text, trunc = reader.decode_line(raw)
            out.append(Line(-1, text, off, len(raw), trunc))
        return out

    # ---- 이벤트 --------------------------------------------------------

    def poll_events(self) -> list:
        out = []
        try:
            while True:
                out.append(self._events.get_nowait())
        except queue.Empty:
            pass
        return out

    def _emit(self, event: object) -> None:
        self._events.put(event)
