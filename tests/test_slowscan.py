"""느린 쿼리 스캔(engine/slowscan.py + LogEngine 파사드) 테스트 — Tk 비의존."""

import time

from engine.events import SlowScanComplete
from engine.logengine import LogEngine
from engine.slowscan import slow_ms

SAMPLE_LINES = [
    "INFO boot",
    "x Time:3 [QET:NORMAL] Query:{",
    "select 1",
    "}[END]",
    "y Time:1500 [QET:NORMAL]",
    "plain",
    "z Time:25000 [QET:SLOW]",
    "Uptime:99999 not a query time",
]


# ---- slow_ms(순수 함수) ----------------------------------------------------


def test_slow_ms_no_time():
    assert slow_ms("plain log line", 0) is None


def test_slow_ms_threshold():
    assert slow_ms("Time:500 [QET:NORMAL]", 1000) is None
    assert slow_ms("Time:1500 [QET:NORMAL]", 1000) == 1500
    assert slow_ms("Time:1000", 1000) == 1000  # 경계 포함


def test_slow_ms_takes_max_of_multiple():
    assert slow_ms("a Time:200 b Time:3000 c Time:800", 100) == 3000


def test_slow_ms_word_boundary_excludes_uptime():
    assert slow_ms("Uptime:99999", 0) is None


# ---- LogEngine 통합 --------------------------------------------------------


def _open_engine(tmp_path, name, data: bytes) -> LogEngine:
    p = tmp_path / name
    p.write_bytes(data)
    eng = LogEngine()
    eng.open(str(p))
    return eng


def _wait_slow_complete(eng, timeout=5.0) -> list:
    deadline = time.time() + timeout
    events = []
    while time.time() < deadline:
        events += eng.poll_events()
        if any(isinstance(e, SlowScanComplete) for e in events):
            return events
        time.sleep(0.01)
    raise AssertionError("느린 쿼리 스캔이 제한 시간 안에 끝나지 않음")


def test_engine_slow_scan_finds_hits(tmp_path):
    eng = _open_engine(tmp_path, "s.log", ("\n".join(SAMPLE_LINES) + "\n").encode("utf-8"))
    try:
        eng.start_slow_scan(1000)
        _wait_slow_complete(eng)
        assert eng.slow_hit_count() == 2
        assert eng.slow_hit(0) == (4, 1500)
        assert eng.slow_hit(1) == (6, 25000)
        assert eng.slow_hit(2) is None
        assert eng.is_slow_scan_complete()
        assert not eng.slow_scan_capped()
    finally:
        eng.close()


def test_engine_slow_scan_threshold_zero_counts_all_times(tmp_path):
    eng = _open_engine(tmp_path, "z.log", ("\n".join(SAMPLE_LINES) + "\n").encode("utf-8"))
    try:
        eng.start_slow_scan(0)
        _wait_slow_complete(eng)
        # Time: 줄 3개(3/1500/25000) — Uptime: 줄은 단어 경계로 제외
        assert eng.slow_hit_count() == 3
        assert eng.slow_hit(0) == (1, 3)
    finally:
        eng.close()


def test_engine_slow_scan_utf16(tmp_path):
    data = b"\xff\xfe" + ("\n".join(SAMPLE_LINES) + "\n").encode("utf-16-le")
    eng = _open_engine(tmp_path, "u16.log", data)
    try:
        eng.start_slow_scan(1000)
        _wait_slow_complete(eng)
        assert eng.slow_hit_count() == 2
        assert eng.slow_hit(0) == (4, 1500)
    finally:
        eng.close()


def test_engine_stop_slow_scan_clears(tmp_path):
    eng = _open_engine(tmp_path, "stop.log", ("\n".join(SAMPLE_LINES) + "\n").encode("utf-8"))
    try:
        eng.start_slow_scan(0)
        eng.stop_slow_scan()
        assert eng.slow_hit_count() == 0
        assert eng.slow_hit(0) is None
        assert eng.is_slow_scan_complete()
    finally:
        eng.close()


def test_engine_restart_replaces_previous_scan(tmp_path):
    eng = _open_engine(tmp_path, "re.log", ("\n".join(SAMPLE_LINES) + "\n").encode("utf-8"))
    try:
        eng.start_slow_scan(10**9)  # 일치 없음
        _wait_slow_complete(eng)
        assert eng.slow_hit_count() == 0
        eng.start_slow_scan(1000)   # 재시작 — 이전 스캔 대체
        _wait_slow_complete(eng)
        assert eng.slow_hit_count() == 2
    finally:
        eng.close()
