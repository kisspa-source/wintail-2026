"""Sparse 체크포인트 인덱스 (순수 저장/조회).

모든 줄의 오프셋을 저장하면 5GB(약 5천만 줄)에서 ~400MB가 되어 저메모리
요구에 위배된다. 대신 일정 간격(라인 수 또는 바이트)으로 line 시작 오프셋만
체크포인트로 저장한다. 임의 라인 K로 점프할 때는 K 직전 체크포인트를 bisect로
찾아 그 오프셋부터 forward scan한다(스캔 범위는 인덱서가 체크포인트 간격으로
제한한다).

이 클래스는 I/O를 하지 않는다 — 스캔과 체크포인트 배치 정책은 BackgroundIndexer가
담당하고, 여기서는 저장과 조회, 그리고 total_lines/indexed_bytes/complete 상태만
관리한다. 워커 스레드의 변경과 UI 스레드의 조회가 공존하므로 락으로 보호한다.
"""

from __future__ import annotations

import threading
from array import array
from bisect import bisect_right


class FileIndex:
    def __init__(self, start_offset: int = 0):
        self._lock = threading.Lock()
        self.reset(start_offset)

    def reset(self, start_offset: int = 0) -> None:
        with self._lock:
            # 'q' = signed 64-bit. 5GB+ 오프셋과 라인 번호를 담는다.
            self._cp_lines = array("q", [0])
            self._cp_offsets = array("q", [start_offset])
            self.total_lines = 0
            self.indexed_bytes = start_offset
            self.complete = False

    def add_checkpoint(self, line_no: int, offset: int) -> None:
        """라인 시작 체크포인트 추가. line_no는 엄격히 증가해야 한다."""
        with self._lock:
            if line_no <= self._cp_lines[-1]:
                raise ValueError(
                    f"체크포인트 line_no는 엄격히 증가해야 함: {line_no} <= {self._cp_lines[-1]}"
                )
            self._cp_lines.append(line_no)
            self._cp_offsets.append(offset)

    def checkpoint_before(self, line_no: int) -> tuple[int, int]:
        """line_no 이하의 가장 가까운 체크포인트 (cp_line, cp_offset)."""
        with self._lock:
            i = bisect_right(self._cp_lines, line_no) - 1
            if i < 0:
                i = 0
            return (self._cp_lines[i], self._cp_offsets[i])

    def update(self, total_lines: int, indexed_bytes: int) -> None:
        self.total_lines = total_lines
        self.indexed_bytes = indexed_bytes

    def mark_complete(self) -> None:
        self.complete = True

    @property
    def checkpoint_count(self) -> int:
        return len(self._cp_lines)
