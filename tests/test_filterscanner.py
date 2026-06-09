"""Matcher + FilterScanner 단위 테스트.

Matcher: 부분문자열/정규식/대소문자 무시, 하이라이트용 span 탐색.
FilterScanner: 전체 스캔으로 매칭 라인 번호 누적(hide 모드), dense cap, 완료 이벤트.
"""

from engine.encoding import info_for_codec
from engine.events import FilterComplete
from engine.filereader import FileReader
from engine.filterscanner import FilterScanner, Matcher


# ---- Matcher --------------------------------------------------------------


def test_matcher_substring():
    m = Matcher("ERROR")
    assert m.matches_text("2020 ERROR boom") is True
    assert m.matches_text("info ok") is False


def test_matcher_ignore_case():
    m = Matcher("error", ignore_case=True)
    assert m.matches_text("ERROR boom") is True
    assert m.matches_text("Error here") is True


def test_matcher_regex():
    m = Matcher(r"\d{3}-\d{4}", regex=True)
    assert m.matches_text("call 123-4567 now") is True
    assert m.matches_text("no digits") is False


def test_matcher_regex_ignore_case():
    m = Matcher(r"err", regex=True, ignore_case=True)
    assert m.matches_text("big ERR here") is True


def test_matcher_find_spans():
    m = Matcher("ab")
    assert m.find_spans("ab xyz ab") == [(0, 2), (7, 9)]


def test_matcher_find_spans_regex():
    m = Matcher(r"\d+", regex=True)
    assert m.find_spans("a12 b3") == [(1, 3), (5, 6)]


def test_matcher_empty_pattern_matches_nothing():
    m = Matcher("")
    assert m.matches_text("anything") is False
    assert m.find_spans("anything") == []


def test_matcher_invalid_regex_is_inert():
    m = Matcher("(", regex=True)  # 잘못된 정규식
    assert m.valid is False
    assert m.matches_text("(") is False


# ---- FilterScanner --------------------------------------------------------


def make_reader(tmp_path, data, codec="utf-8"):
    p = tmp_path / "log.txt"
    p.write_bytes(data)
    return FileReader(str(p), info_for_codec(codec))


def run_scan(reader, matcher, events, **kw):
    sc = FilterScanner(
        reader, events.append, matcher,
        start_offset=0, read_chunk=4096, line_cap=65536,
        total_size=reader.size(), **kw,
    )
    sc.run()
    return sc


def test_scan_hide_collects_line_numbers(tmp_path):
    data = b"".join(
        (b"ERROR %d\n" % i) if i % 3 == 0 else (b"info %d\n" % i) for i in range(30)
    )
    reader = make_reader(tmp_path, data)
    events: list = []
    sc = run_scan(reader, Matcher("ERROR"), events)
    assert sc.matched_count() == 10  # 0,3,...,27
    assert sc.match_at(0) == 0
    assert sc.match_at(1) == 3
    assert sc.match_at(9) == 27
    assert any(isinstance(e, FilterComplete) for e in events)


def test_scan_records_offsets(tmp_path):
    # "aa\nERR\nbb\nERR\n" : ERR는 line1(off3), line3(off10)
    reader = make_reader(tmp_path, b"aa\nERR\nbb\nERR\n")
    events: list = []
    sc = run_scan(reader, Matcher("ERR"), events)
    assert sc.matched_count() == 2
    assert (sc.match_at(0), sc.match_at(1)) == (1, 3)
    assert (sc.offset_at(0), sc.offset_at(1)) == (3, 10)
    assert reader.read(sc.offset_at(0), 4) == b"ERR\n"


def test_scan_regex(tmp_path):
    reader = make_reader(tmp_path, b"a1\nbb\nc3\nd\ne5\n")
    events: list = []
    sc = run_scan(reader, Matcher(r"\d", regex=True), events)
    assert sc.matched_count() == 3
    assert [sc.match_at(i) for i in range(3)] == [0, 2, 4]


def test_scan_korean_cp949(tmp_path):
    reader = make_reader(tmp_path, "에러\n정보\n에러\n".encode("cp949"), codec="cp949")
    events: list = []
    sc = run_scan(reader, Matcher("에러"), events)
    assert sc.matched_count() == 2
    assert [sc.match_at(i) for i in range(2)] == [0, 2]


def test_scan_no_matches(tmp_path):
    reader = make_reader(tmp_path, b"a\nb\nc\n")
    events: list = []
    sc = run_scan(reader, Matcher("zzz"), events)
    assert sc.matched_count() == 0
    assert any(isinstance(e, FilterComplete) for e in events)


def test_dense_cap_stops_accumulating(tmp_path):
    reader = make_reader(tmp_path, b"".join(b"x\n" for _ in range(100)))
    events: list = []
    sc = run_scan(reader, Matcher("x"), events, dense_cap=10)
    assert sc.matched_count() == 10
    assert sc.capped is True


def test_stop_event_cancels(tmp_path):
    import threading

    reader = make_reader(tmp_path, b"".join(b"x %d\n" % i for i in range(10000)))
    events: list = []
    stop = threading.Event()
    stop.set()
    sc = FilterScanner(
        reader, events.append, Matcher("x"),
        start_offset=0, read_chunk=4096, line_cap=65536,
        total_size=reader.size(), stop_event=stop,
    )
    sc.run()
    assert sc.matched_count() < 10000
