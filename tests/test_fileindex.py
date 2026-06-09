"""FileIndex 단위 테스트.

FileIndex는 순수 저장/조회 구조다(I/O·스캔 없음):
  - sparse 체크포인트 (line_no → byte offset) 저장과 bisect 조회
  - total_lines / indexed_bytes / complete 상태
  - 트렁케이션 시 reset
스캔·체크포인트 배치 정책은 BackgroundIndexer가 담당한다.
"""

import pytest

from engine.fileindex import FileIndex


def test_empty_index_has_checkpoint_zero():
    idx = FileIndex(start_offset=0)
    assert idx.total_lines == 0
    assert idx.complete is False
    assert idx.checkpoint_before(0) == (0, 0)


def test_start_offset_is_first_checkpoint():
    idx = FileIndex(start_offset=3)  # UTF-8 BOM 예
    assert idx.checkpoint_before(0) == (0, 3)
    assert idx.indexed_bytes == 3


def test_add_and_lookup_checkpoints():
    idx = FileIndex(start_offset=0)
    idx.add_checkpoint(2, 4)
    idx.add_checkpoint(4, 8)
    assert idx.checkpoint_before(0) == (0, 0)
    assert idx.checkpoint_before(1) == (0, 0)
    assert idx.checkpoint_before(2) == (2, 4)
    assert idx.checkpoint_before(3) == (2, 4)
    assert idx.checkpoint_before(4) == (4, 8)
    assert idx.checkpoint_before(100) == (4, 8)


def test_add_checkpoint_must_strictly_increase():
    idx = FileIndex()
    idx.add_checkpoint(2, 4)
    with pytest.raises(ValueError):
        idx.add_checkpoint(2, 6)  # 같은 라인 번호
    with pytest.raises(ValueError):
        idx.add_checkpoint(1, 2)  # 감소


def test_update_total_and_bytes():
    idx = FileIndex()
    idx.update(total_lines=100, indexed_bytes=5000)
    assert idx.total_lines == 100
    assert idx.indexed_bytes == 5000


def test_mark_complete():
    idx = FileIndex()
    assert idx.complete is False
    idx.mark_complete()
    assert idx.complete is True


def test_reset_clears_everything():
    idx = FileIndex(start_offset=0)
    idx.add_checkpoint(2, 4)
    idx.update(total_lines=10, indexed_bytes=20)
    idx.mark_complete()

    idx.reset(start_offset=5)
    assert idx.total_lines == 0
    assert idx.indexed_bytes == 5
    assert idx.complete is False
    assert idx.checkpoint_before(0) == (0, 5)
    assert idx.checkpoint_count == 1


def test_checkpoint_count():
    idx = FileIndex()
    for i in range(1, 1001):
        idx.add_checkpoint(i * 2, i * 100)
    assert idx.checkpoint_count == 1001  # cp0 포함
