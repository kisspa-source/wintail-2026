"""라인 이터레이터 — LogEngine(랜덤 접근)과 FilterScanner(전체 스캔)가 공유.

주어진 오프셋(라인 시작)부터 EOF까지 (line_no, byte_off, raw_bytes)를 지연 생성한다.
초장문 줄(개행 없이 read_chunk를 초과)은 line_cap에서 잘라 한 줄로 내보낸 뒤 다음
개행까지 건너뛰어, 버퍼가 무한히 커지지 않도록 한다.
"""

from __future__ import annotations

from collections.abc import Iterator

from engine.filereader import FileReader


def iter_lines(
    reader: FileReader,
    start_offset: int,
    start_line_no: int,
    *,
    read_chunk: int,
    line_cap: int,
) -> Iterator[tuple[int, int, bytes]]:
    nlen = len(reader.info.newline)
    line_no = start_line_no
    pos = start_offset
    buf = b""
    buf_start = start_offset
    skipping = False

    while True:
        chunk = reader.read(pos, read_chunk)
        if not chunk:
            break
        buf += chunk
        pos += len(chunk)

        if skipping:
            nls = reader.find_newlines(buf)
            if nls:
                advance = nls[0] + nlen
                buf = buf[advance:]
                buf_start += advance
                skipping = False
            else:
                keep = min(nlen, len(buf))
                buf_start += len(buf) - keep
                buf = buf[len(buf) - keep :]
                continue

        nls = reader.find_newlines(buf)
        if not nls:
            if len(buf) > line_cap:
                yield (line_no, buf_start, buf)
                line_no += 1
                buf_start += len(buf)
                buf = b""
                skipping = True
            continue

        last = 0
        for p in nls:
            raw = buf[last : p + nlen]
            yield (line_no, buf_start + last, raw)
            line_no += 1
            last = p + nlen
        buf = buf[last:]
        buf_start += last

    if not skipping and buf:
        yield (line_no, buf_start, buf)
