"""EncodingDetector 단위 테스트.

검증 순서: BOM 스니프 → strict UTF-8 → CP949 → latin-1 폴백.
EncodingInfo가 라인 분할에 필요한 (codec, bom_len, unit_size, newline)을
올바르게 제공하는지 함께 확인한다.
"""

from engine.encoding import detect, info_for_codec


def test_detects_utf8_bom():
    info = detect(b"\xef\xbb\xbf" + "안녕 hello".encode("utf-8"))
    assert info.codec == "utf-8"
    assert info.bom_len == 3
    assert info.unit_size == 1
    assert info.newline == b"\n"


def test_detects_utf16_le_bom():
    info = detect(b"\xff\xfe" + "log".encode("utf-16-le"))
    assert info.codec == "utf-16-le"
    assert info.bom_len == 2
    assert info.unit_size == 2
    assert info.newline == b"\x0a\x00"


def test_detects_utf16_be_bom():
    info = detect(b"\xfe\xff" + "log".encode("utf-16-be"))
    assert info.codec == "utf-16-be"
    assert info.bom_len == 2
    assert info.unit_size == 2
    assert info.newline == b"\x00\x0a"


def test_plain_ascii_is_utf8():
    info = detect(b"INFO ready\nERROR boom\n")
    assert info.codec == "utf-8"
    assert info.bom_len == 0


def test_korean_utf8_no_bom_is_utf8():
    info = detect("로그 시작\n에러 발생\n".encode("utf-8"))
    assert info.codec == "utf-8"
    assert info.bom_len == 0


def test_korean_cp949_is_cp949():
    # CP949 한글은 UTF-8로 strict 디코드 시 실패 → cp949로 감지되어야 한다.
    info = detect("로그 시작\n에러 발생\n".encode("cp949"))
    assert info.codec == "cp949"


def test_invalid_bytes_fall_back_to_latin1():
    # UTF-8/CP949 둘 다 깨지는 바이트열은 절대 실패하지 않는 latin-1로.
    info = detect(b"\xff\xfe\x00\x81\x82\x83 raw \x9f bytes")
    # (앞 2바이트가 utf-16 BOM과 겹치지 않도록) 순수 잡음 케이스
    assert info.codec in ("latin-1", "utf-16-le")  # BOM 우선 규칙 허용


def test_pure_noise_falls_back_to_latin1():
    info = detect(b"\x81\x82\xed\xa0\x80\xff\xfa garbage")
    assert info.codec == "latin-1"


def test_trailing_incomplete_multibyte_still_utf8():
    # 64KB 샘플 끝에서 잘린 멀티바이트 한 글자가 있어도 UTF-8로 봐야 한다.
    full = "한국어 로그 ".encode("utf-8")
    truncated = full[:-1]  # 마지막 글자 한 바이트 잘림
    info = detect(b"normal ascii line\n" + truncated)
    assert info.codec == "utf-8"


def test_info_for_codec_manual_override_cp949():
    info = info_for_codec("cp949")
    assert info.codec == "cp949"
    assert info.unit_size == 1
    assert info.newline == b"\n"


def test_info_for_codec_utf16le_with_bom_sample():
    info = info_for_codec("utf-16-le", sample=b"\xff\xfe" + "x".encode("utf-16-le"))
    assert info.codec == "utf-16-le"
    assert info.bom_len == 2


def test_info_for_codec_utf16le_without_bom():
    info = info_for_codec("utf-16-le", sample="x".encode("utf-16-le"))
    assert info.codec == "utf-16-le"
    assert info.bom_len == 0
    assert info.unit_size == 2
