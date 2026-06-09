"""인코딩 감지.

검증 순서:
  1. BOM 스니프 (UTF-8/UTF-16 LE/BE) — 결정적, 최우선
  2. strict UTF-8 시도 (끝이 잘린 멀티바이트는 허용)
  3. strict CP949(EUC-KR superset) 시도
  4. latin-1 폴백 — 절대 실패하지 않으므로 파일은 항상 열린다

EncodingInfo는 라인 분할에 필요한 정보를 함께 들고 다닌다:
  - codec     : 바이트 슬라이스를 str로 디코드할 때 쓰는 코덱 이름
  - bom_len   : 파일 시작에서 건너뛸 BOM 바이트 수
  - unit_size : 코드 유닛 크기(1 또는 2). UTF-16의 seek/체크포인트 정렬에 사용
  - newline   : 이 인코딩에서 개행을 나타내는 바이트 패턴
"""

from __future__ import annotations

import codecs
from dataclasses import dataclass

# BOM 시그니처
_BOM_UTF8 = b"\xef\xbb\xbf"
_BOM_UTF16_LE = b"\xff\xfe"
_BOM_UTF16_BE = b"\xfe\xff"


@dataclass(frozen=True)
class EncodingInfo:
    codec: str
    label: str
    bom_len: int
    unit_size: int
    newline: bytes


# 코덱별 기본 속성 (bom_len 제외 — bom_len은 실제 바이트로 결정)
_PROFILES: dict[str, tuple[str, int, bytes]] = {
    # codec       : (label,            unit_size, newline)
    "utf-8": ("UTF-8", 1, b"\n"),
    "utf-16-le": ("UTF-16 LE", 2, b"\x0a\x00"),
    "utf-16-be": ("UTF-16 BE", 2, b"\x00\x0a"),
    "cp949": ("CP949 (EUC-KR)", 1, b"\n"),
    "latin-1": ("Latin-1", 1, b"\n"),
}

# 코덱별 BOM (수동 오버라이드 시 샘플에서 BOM 유무를 판정하는 데 사용)
_CODEC_BOM: dict[str, bytes] = {
    "utf-8": _BOM_UTF8,
    "utf-16-le": _BOM_UTF16_LE,
    "utf-16-be": _BOM_UTF16_BE,
}


def _make_info(codec: str, bom_len: int) -> EncodingInfo:
    label, unit_size, newline = _PROFILES[codec]
    if bom_len and codec == "utf-8":
        label = "UTF-8 (BOM)"
    return EncodingInfo(codec=codec, label=label, bom_len=bom_len, unit_size=unit_size, newline=newline)


def _decodes_clean(sample: bytes, codec: str) -> bool:
    """sample을 codec으로 strict 디코드할 수 있는지.

    incremental decoder를 final=False로 사용하므로, 샘플 끝에서 잘린
    멀티바이트 시퀀스는 버퍼링되어 오류로 보지 않는다(진짜 잘못된 바이트만 실패).
    """
    decoder = codecs.getincrementaldecoder(codec)(errors="strict")
    try:
        decoder.decode(sample, False)
        return True
    except UnicodeDecodeError:
        return False


def detect(sample: bytes) -> EncodingInfo:
    """파일 앞부분 샘플(권장 ~64KB)로 인코딩을 감지한다."""
    if sample.startswith(_BOM_UTF8):
        return _make_info("utf-8", 3)
    if sample.startswith(_BOM_UTF16_LE):
        return _make_info("utf-16-le", 2)
    if sample.startswith(_BOM_UTF16_BE):
        return _make_info("utf-16-be", 2)

    if _decodes_clean(sample, "utf-8"):
        return _make_info("utf-8", 0)
    if _decodes_clean(sample, "cp949"):
        return _make_info("cp949", 0)
    return _make_info("latin-1", 0)


def info_for_codec(codec: str, sample: bytes = b"") -> EncodingInfo:
    """수동 오버라이드용. 주어진 코덱의 EncodingInfo를 만든다.

    샘플이 해당 코덱의 BOM으로 시작하면 bom_len을 그만큼 설정한다.
    """
    codec = codec.lower()
    if codec not in _PROFILES:
        raise ValueError(f"지원하지 않는 코덱: {codec!r}")
    bom = _CODEC_BOM.get(codec, b"")
    bom_len = len(bom) if bom and sample.startswith(bom) else 0
    return _make_info(codec, bom_len)


def supported_codecs() -> list[str]:
    """UI 코덱 드롭다운용 목록."""
    return ["utf-8", "utf-16-le", "utf-16-be", "cp949", "latin-1"]
