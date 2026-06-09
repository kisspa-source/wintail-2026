"""FileReader 단위 테스트.

- read/size: 바이트 I/O
- find_newlines/count_newlines: 인코딩 인지 개행 탐지 (UTF-16 2바이트 정렬)
- decode_line: 개행/CR 제거, 디코드, MAX_RENDER_BYTES 클리핑
"""

from engine.encoding import info_for_codec
from engine.filereader import FileReader


def make_reader(tmp_path, data: bytes, codec="utf-8", **kw):
    p = tmp_path / "log.bin"
    p.write_bytes(data)
    return FileReader(str(p), info_for_codec(codec), **kw)


def test_read_returns_bytes(tmp_path):
    r = make_reader(tmp_path, b"hello world")
    assert r.read(0, 5) == b"hello"
    assert r.read(6, 5) == b"world"
    r.close()


def test_size_reflects_file(tmp_path):
    r = make_reader(tmp_path, b"hello world")
    assert r.size() == 11
    r.close()


def test_read_past_eof_is_clamped(tmp_path):
    r = make_reader(tmp_path, b"abc")
    assert r.read(1, 999) == b"bc"
    r.close()


def test_find_newlines_ascii(tmp_path):
    r = make_reader(tmp_path, b"x")
    assert r.find_newlines(b"a\nbb\nccc\n") == [1, 4, 8]
    r.close()


def test_count_newlines_ascii(tmp_path):
    r = make_reader(tmp_path, b"x")
    assert r.count_newlines(b"a\nb\nc") == 2
    r.close()


def test_find_newlines_utf16le_rejects_misaligned(tmp_path):
    # 41 0a 00 11 0a 00 : 미정렬 0a00@idx1 은 무시, 정렬 개행@idx4 만 인정
    r = make_reader(tmp_path, b"x", codec="utf-16-le")
    data = (chr(0x0A41) + chr(0x1100)).encode("utf-16-le") + b"\x0a\x00"
    assert r.find_newlines(data) == [4]
    assert r.count_newlines(data) == 1
    r.close()


def test_decode_line_strips_lf(tmp_path):
    r = make_reader(tmp_path, b"x")
    text, trunc = r.decode_line(b"hello\n")
    assert text == "hello"
    assert trunc is False


def test_decode_line_strips_crlf(tmp_path):
    r = make_reader(tmp_path, b"x")
    text, trunc = r.decode_line(b"hello\r\n")
    assert text == "hello"
    assert trunc is False


def test_decode_line_no_trailing_newline(tmp_path):
    r = make_reader(tmp_path, b"x")
    text, trunc = r.decode_line(b"last line no nl")
    assert text == "last line no nl"
    assert trunc is False


def test_decode_line_utf8_korean(tmp_path):
    r = make_reader(tmp_path, b"x")
    text, _ = r.decode_line("에러 발생\n".encode("utf-8"))
    assert text == "에러 발생"


def test_decode_line_cp949_korean(tmp_path):
    r = make_reader(tmp_path, b"x", codec="cp949")
    text, _ = r.decode_line("안녕\n".encode("cp949"))
    assert text == "안녕"


def test_decode_line_utf16le_korean_crlf(tmp_path):
    r = make_reader(tmp_path, b"x", codec="utf-16-le")
    raw = "에러\r\n".encode("utf-16-le")  # ... 0d 00 0a 00
    text, trunc = r.decode_line(raw)
    assert text == "에러"
    assert trunc is False


def test_decode_line_clips_long_line(tmp_path):
    r = make_reader(tmp_path, b"x", max_line_bytes=8192)
    text, trunc = r.decode_line(b"A" * 10000 + b"\n")
    assert trunc is True
    assert len(text) == 8192


def test_last_newline_ascii(tmp_path):
    r = make_reader(tmp_path, b"x")
    assert r.last_newline(b"a\nbb\nccc") == 4
    assert r.last_newline(b"no newline here") == -1
    r.close()


def test_last_newline_utf16le_aligned(tmp_path):
    r = make_reader(tmp_path, b"x", codec="utf-16-le")
    # 41 0a 00 11 | 0a 00 | 41 0a : 정렬 개행은 idx4 뿐
    data = (chr(0x0A41) + chr(0x1100)).encode("utf-16-le") + b"\x0a\x00" + chr(0x0A41).encode("utf-16-le")
    assert r.last_newline(data) == 4
    r.close()


def test_decode_line_clip_aligns_utf16(tmp_path):
    # UTF-16에서 클리핑은 2바이트 경계로 맞춰져 깨진 유닛이 남지 않아야 한다.
    r = make_reader(tmp_path, b"x", codec="utf-16-le", max_line_bytes=11)
    raw = ("가" * 10).encode("utf-16-le")  # 20바이트
    text, trunc = r.decode_line(raw)
    assert trunc is True
    # 11 → 짝수 10바이트로 정렬 → 5글자
    assert text == "가" * 5
