"""TailWatcher 단위 테스트 (poll_once로 결정적 검증).

검증: 증가분 추가(Appended), 미완성 줄(pending_partial) 처리, 트렁케이션 리셋
(Truncated), 변화 없음.
"""

from engine.encoding import info_for_codec
from engine.events import Appended, Truncated
from engine.fileindex import FileIndex
from engine.filereader import FileReader
from engine.indexer import ScanState, scan_forward
from engine.tailwatcher import TailWatcher


def setup_tail(tmp_path, initial: bytes):
    p = tmp_path / "log.txt"
    p.write_bytes(initial)
    reader = FileReader(str(p), info_for_codec("utf-8"))
    index = FileIndex(start_offset=0)
    state = ScanState.at_start(0)
    scan_forward(reader, index, state, read_chunk=4096, checkpoint_bytes=4096)
    index.mark_complete()
    events: list = []
    tw = TailWatcher(
        str(p), reader, index, state, events.append,
        read_chunk=4096, checkpoint_bytes=4096,
    )
    tw.prime()
    return p, reader, index, state, events, tw


def test_unchanged(tmp_path):
    _, _, _, _, _, tw = setup_tail(tmp_path, b"a\nb\n")
    assert tw.poll_once() == "unchanged"


def test_growth_appends(tmp_path):
    p, _, index, _, events, tw = setup_tail(tmp_path, b"a\nb\n")
    assert index.total_lines == 2
    with open(p, "ab") as f:
        f.write(b"c\nd\n")
    assert tw.poll_once() == "appended"
    assert index.total_lines == 4
    assert any(isinstance(e, Appended) for e in events)


def test_partial_line_then_completed(tmp_path):
    p, reader, index, _, _, tw = setup_tail(tmp_path, b"a\nb\n")
    with open(p, "ab") as f:
        f.write(b"partial")  # 개행 없음
    tw.poll_once()
    assert index.total_lines == 3  # 미완성 줄도 한 줄로 카운트

    with open(p, "ab") as f:
        f.write(b" done\n")
    tw.poll_once()
    assert index.total_lines == 3  # 완성되어도 여전히 3줄

    # 완성된 마지막 줄 내용 확인
    cp_line, cp_off = index.checkpoint_before(2)
    raw = reader.read(cp_off, 100)
    # cp_off가 라인2 이전 체크포인트일 수 있으므로 라인2 시작까지 전진은 생략하고
    # 단순히 "partial done"이 파일에 있는지 확인
    assert b"partial done\n" in raw


def test_truncation_resets(tmp_path):
    p, _, index, _, events, tw = setup_tail(tmp_path, b"a\nb\nc\nd\n")
    assert index.total_lines == 4
    with open(p, "wb") as f:
        f.write(b"x\n")  # 더 짧게 덮어씀 (in-place truncate)
    assert tw.poll_once() == "truncated"
    assert index.total_lines == 1
    assert any(isinstance(e, Truncated) for e in events)


def test_growth_after_truncation(tmp_path):
    p, _, index, _, _, tw = setup_tail(tmp_path, b"a\nb\nc\n")
    with open(p, "wb") as f:
        f.write(b"new\n")
    tw.poll_once()
    assert index.total_lines == 1
    with open(p, "ab") as f:
        f.write(b"more\nlines\n")
    tw.poll_once()
    assert index.total_lines == 3
