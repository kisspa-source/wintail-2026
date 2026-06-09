"""BackgroundIndexer 단위 테스트 (동기 run()으로 결정적 검증).

검증: 라인 수 카운트(종료/미종료/빈 파일), 체크포인트가 실제 라인 시작에
놓이는지, BOM start_offset 처리, 완료 이벤트.
"""

from engine.encoding import detect, info_for_codec
from engine.events import IndexComplete
from engine.fileindex import FileIndex
from engine.filereader import FileReader
from engine.indexer import BackgroundIndexer


def build(tmp_path, data: bytes, **params):
    p = tmp_path / "log.txt"
    p.write_bytes(data)
    info = detect(data[:65536])
    reader = FileReader(str(p), info)
    index = FileIndex(start_offset=info.bom_len)
    events = []
    indexer = BackgroundIndexer(
        reader, index, events.append, start_offset=info.bom_len, **params
    )
    indexer.run()
    return reader, index, events


def test_counts_terminated(tmp_path):
    _, index, _ = build(tmp_path, b"a\nbb\nccc\n")
    assert index.total_lines == 3
    assert index.complete is True


def test_counts_unterminated(tmp_path):
    _, index, _ = build(tmp_path, b"a\nbb\nccc")
    assert index.total_lines == 3


def test_counts_empty(tmp_path):
    _, index, _ = build(tmp_path, b"")
    assert index.total_lines == 0
    assert index.complete is True


def test_counts_single_newline(tmp_path):
    _, index, _ = build(tmp_path, b"\n")
    assert index.total_lines == 1


def test_checkpoints_land_on_line_starts(tmp_path):
    # 1000줄, 각 10바이트("line00000\n"). 작은 청크/체크포인트로 다수 체크포인트 강제.
    data = b"".join(b"line%05d\n" % i for i in range(1000))
    reader, index, _ = build(tmp_path, data, read_chunk=777, checkpoint_bytes=777)
    assert index.total_lines == 1000
    assert index.checkpoint_count > 1
    # 임의 라인들의 체크포인트가 정확히 그 라인의 시작 바이트를 가리키는지 검증
    for target in (1, 250, 500, 999):
        cp_line, cp_off = index.checkpoint_before(target)
        assert cp_line <= target
        assert reader.read(cp_off, 10) == b"line%05d\n" % cp_line


def test_emits_complete_event(tmp_path):
    _, _, events = build(tmp_path, b"a\nb\nc\n")
    completes = [e for e in events if isinstance(e, IndexComplete)]
    assert len(completes) == 1
    assert completes[0].total_lines == 3


def test_utf8_bom_checkpoint_offset(tmp_path):
    _, index, _ = build(tmp_path, b"\xef\xbb\xbf" + b"a\nb\n")
    assert index.total_lines == 2
    cp_line, cp_off = index.checkpoint_before(0)
    assert (cp_line, cp_off) == (0, 3)  # BOM 3바이트 뒤에서 시작


def test_stop_event_cancels(tmp_path):
    import threading

    big = b"".join(b"line%06d\n" % i for i in range(20000))
    p = tmp_path / "big.txt"
    p.write_bytes(big)
    info = info_for_codec("utf-8")
    reader = FileReader(str(p), info)
    index = FileIndex()
    stop = threading.Event()
    stop.set()  # 시작 전에 정지 → 거의 아무것도 안 함
    indexer = BackgroundIndexer(reader, index, lambda e: None, stop_event=stop)
    indexer.run()
    assert index.complete is False
    assert index.total_lines < 20000
