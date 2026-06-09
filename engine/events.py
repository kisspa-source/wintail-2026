"""엔진 → UI 이벤트 타입과 라인 레코드.

워커 스레드(인덱서/Tail/필터)는 이 이벤트들을 큐에 넣고, UI 스레드가
poll_events로 드레인한다. 모두 불변 데이터 컨테이너다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Line:
    """표시용 라인 레코드. text는 이미 디코드·개행제거·클리핑된 상태."""

    line_no: int
    text: str
    byte_off: int
    length: int
    truncated: bool


# ---- 이벤트 -------------------------------------------------------------


@dataclass(frozen=True)
class Opened:
    path: str
    size: int
    encoding: str


@dataclass(frozen=True)
class EncodingDetected:
    codec: str
    label: str


@dataclass(frozen=True)
class IndexProgress:
    total_lines: int
    indexed_bytes: int
    size: int


@dataclass(frozen=True)
class IndexComplete:
    total_lines: int
    size: int


@dataclass(frozen=True)
class Appended:
    """Tail로 새 데이터가 추가됨."""

    total_lines: int
    size: int


@dataclass(frozen=True)
class Truncated:
    """파일이 줄어들거나 로테이션됨 — 인덱스 리셋 후 재시작."""

    new_size: int


@dataclass(frozen=True)
class FilterProgress:
    matched: int
    scanned_bytes: int
    size: int


@dataclass(frozen=True)
class FilterComplete:
    matched: int


@dataclass(frozen=True)
class FileError:
    message: str
