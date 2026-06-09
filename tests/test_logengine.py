"""LogEngine 파사드 테스트 (실제 백그라운드 스레드 사용, 인덱싱 완료까지 대기).

검증: open/인코딩 감지, get_lines 임의 접근(체크포인트 경유), 끝/미종료 처리,
get_tail, 이벤트, 초장문 줄 클리핑.
"""

import time

from engine.events import IndexComplete, Opened
from engine.logengine import LogEngine


def open_engine(tmp_path, data: bytes, name="log.txt", **engine_kw):
    p = tmp_path / name
    p.write_bytes(data)
    eng = LogEngine(**engine_kw)
    eng.open(str(p))
    for _ in range(2000):
        if eng.is_index_complete():
            break
        time.sleep(0.002)
    assert eng.is_index_complete(), "인덱싱이 시간 내에 끝나지 않음"
    return eng


def test_get_total_and_basic_lines(tmp_path):
    data = b"".join(b"line%03d\n" % i for i in range(100))
    eng = open_engine(tmp_path, data)
    assert eng.get_total_lines() == 100
    lines = eng.get_lines(0, 3)
    assert [l.text for l in lines] == ["line000", "line001", "line002"]
    assert [l.line_no for l in lines] == [0, 1, 2]
    eng.close()


def test_random_access_across_checkpoints(tmp_path):
    data = b"".join(b"L%05d\n" % i for i in range(5000))
    eng = open_engine(tmp_path, data, read_chunk=4096, checkpoint_bytes=4096)
    lines = eng.get_lines(2500, 2)
    assert [l.text for l in lines] == ["L02500", "L02501"]
    assert lines[0].line_no == 2500
    eng.close()


def test_get_lines_near_end_clamps_count(tmp_path):
    data = b"".join(b"x%d\n" % i for i in range(10))
    eng = open_engine(tmp_path, data)
    lines = eng.get_lines(8, 5)  # 남은 2줄만
    assert [l.text for l in lines] == ["x8", "x9"]
    eng.close()


def test_unterminated_last_line(tmp_path):
    eng = open_engine(tmp_path, b"a\nb\nc")
    assert eng.get_total_lines() == 3
    assert [l.text for l in eng.get_lines(0, 3)] == ["a", "b", "c"]
    eng.close()


def test_korean_utf8_lines(tmp_path):
    data = "에러 발생\n경고 메시지\n정보\n".encode("utf-8")
    eng = open_engine(tmp_path, data)
    assert [l.text for l in eng.get_lines(0, 3)] == ["에러 발생", "경고 메시지", "정보"]
    eng.close()


def test_cp949_lines(tmp_path):
    data = "안녕\n세계\n".encode("cp949")
    eng = open_engine(tmp_path, data)
    assert [l.text for l in eng.get_lines(0, 2)] == ["안녕", "세계"]
    eng.close()


def test_get_tail(tmp_path):
    data = b"".join(b"line%d\n" % i for i in range(100))
    eng = open_engine(tmp_path, data)
    tail = eng.get_tail(3)
    assert [l.text for l in tail] == ["line97", "line98", "line99"]
    assert [l.line_no for l in tail] == [97, 98, 99]
    eng.close()


def test_events_opened_and_complete(tmp_path):
    eng = open_engine(tmp_path, b"a\nb\n")
    kinds = [type(e) for e in eng.poll_events()]
    assert Opened in kinds
    assert IndexComplete in kinds
    eng.close()


def test_giant_line_exceeding_chunk_is_clipped(tmp_path):
    data = b"B" * 100000 + b"\ntail\n"
    eng = open_engine(tmp_path, data, read_chunk=4096, max_line_bytes=1024)
    assert eng.get_total_lines() == 2
    lines = eng.get_lines(0, 2)
    assert lines[0].truncated is True
    assert len(lines[0].text) == 1024
    assert lines[1].text == "tail"
    assert lines[1].line_no == 1
    eng.close()


def test_empty_file(tmp_path):
    eng = open_engine(tmp_path, b"")
    assert eng.get_total_lines() == 0
    assert eng.get_lines(0, 5) == []
    eng.close()


def test_follow_picks_up_appends(tmp_path):
    p = tmp_path / "log.txt"
    p.write_bytes(b"a\nb\n")
    eng = LogEngine(read_chunk=4096, checkpoint_bytes=4096, poll_interval=0.02)
    eng.open(str(p))
    for _ in range(2000):
        if eng.is_index_complete():
            break
        time.sleep(0.002)
    assert eng.get_total_lines() == 2

    eng.set_follow(True)
    assert eng.is_following() is True
    with open(p, "ab") as f:
        f.write(b"c\nd\ne\n")
    for _ in range(300):
        if eng.get_total_lines() == 5:
            break
        time.sleep(0.01)
    assert eng.get_total_lines() == 5
    assert [l.text for l in eng.get_tail(2)] == ["d", "e"]

    eng.set_follow(False)
    assert eng.is_following() is False
    eng.close()


def test_filter_hide_mode(tmp_path):
    data = b"".join(
        (b"ERROR %d\n" % i) if i % 5 == 0 else (b"ok %d\n" % i) for i in range(50)
    )
    eng = open_engine(tmp_path, data, read_chunk=4096, checkpoint_bytes=4096)
    eng.set_filter("ERROR", mode="hide")
    for _ in range(400):
        if eng.is_filter_complete():
            break
        time.sleep(0.005)
    assert eng.get_filtered_total() == 10
    flines = eng.get_filtered_lines(0, 3)
    assert all("ERROR" in l.text for l in flines)
    assert [l.line_no for l in flines] == [0, 5, 10]
    eng.clear_filter()
    eng.close()


def test_next_match_line(tmp_path):
    # ERROR가 0,10,20,30,40 줄에
    data = b"".join((b"ERROR %d\n" % i) if i % 10 == 0 else (b"ok %d\n" % i) for i in range(50))
    eng = open_engine(tmp_path, data, read_chunk=4096, checkpoint_bytes=4096)
    eng.set_filter("ERROR", mode="highlight")
    assert eng.next_match_line(0, forward=True) == 0     # 시작 줄이 일치면 그 줄
    assert eng.next_match_line(1, forward=True) == 10
    assert eng.next_match_line(11, forward=True) == 20
    assert eng.next_match_line(41, forward=True) is None  # 40 이후 없음
    assert eng.next_match_line(45, forward=False) == 40
    assert eng.next_match_line(19, forward=False) == 10
    assert eng.next_match_line(0, forward=False) == 0
    assert eng.next_match_line(-1, forward=False) is None
    eng.clear_filter()
    assert eng.next_match_line(0, forward=True) is None   # 매처 없으면 None
    eng.close()


def test_match_rank_and_lazy_scan(tmp_path):
    data = b"".join((b"ERROR %d\n" % i) if i % 10 == 0 else (b"ok %d\n" % i) for i in range(50))
    eng = open_engine(tmp_path, data, read_chunk=4096, checkpoint_bytes=4096)
    eng.set_filter("ERROR", mode="highlight")
    assert eng.match_scan_started() is False     # highlight는 lazy(아직 스캔 안 함)
    assert eng.get_filtered_total() == 0
    eng.start_match_scan()
    assert eng.match_scan_started() is True
    for _ in range(400):
        if eng.is_filter_complete():
            break
        time.sleep(0.005)
    assert eng.get_filtered_total() == 5         # 0,10,20,30,40
    assert eng.match_rank(0) == 1
    assert eng.match_rank(20) == 3
    assert eng.match_rank(40) == 5
    assert eng.match_rank(45) == 5               # 45 이하 일치 5개
    eng.clear_filter()
    eng.close()


def test_filter_highlight_spans(tmp_path):
    eng = open_engine(tmp_path, b"a ERROR b ERROR\n")
    eng.set_filter("ERROR", mode="highlight")
    assert eng.match_spans("a ERROR b ERROR") == [(2, 7), (10, 15)]
    eng.clear_filter()
    assert eng.match_spans("a ERROR") == []
    eng.close()
