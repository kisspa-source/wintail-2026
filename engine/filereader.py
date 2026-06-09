"""인코딩 인지 바이트 I/O.

보편 경로는 seek/read 한 가지로 정적·Tail 양쪽을 모두 처리한다.
모든 메서드는 스레드 안전(내부 락으로 seek+read 보호) — 인덱서/Tail/필터/UI
렌더가 같은 핸들을 동시에 써도 안전하다.

UTF-16 안전성:
  newline 패턴(b"\\x0a\\x00" 등)은 2바이트 정렬(짝수 오프셋)에서만 인정한다.
  무관한 코드포인트의 바이트가 미정렬로 우연히 패턴과 겹쳐도 개행으로 오인하지
  않는다. 따라서 read는 항상 unit_size 경계에서 호출되어야 한다.
"""

from __future__ import annotations

import os
import threading

from engine.encoding import EncodingInfo

DEFAULT_MAX_LINE_BYTES = 8192


class FileReader:
    def __init__(self, path: str, info: EncodingInfo, max_line_bytes: int = DEFAULT_MAX_LINE_BYTES):
        self.path = path
        self.info = info
        self.max_line_bytes = max_line_bytes
        self._fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        self._lock = threading.Lock()
        # 캐리지 리턴 패턴 (CRLF의 \r). 인코딩에 맞춰 1 또는 2바이트.
        if info.unit_size == 2:
            self._cr = b"\x0d\x00" if info.codec == "utf-16-le" else b"\x00\x0d"
        else:
            self._cr = b"\r"

    # ---- 바이트 I/O ----------------------------------------------------

    def read(self, offset: int, size: int) -> bytes:
        if size <= 0:
            return b""
        with self._lock:
            os.lseek(self._fd, offset, os.SEEK_SET)
            return os.read(self._fd, size)

    def size(self) -> int:
        return os.fstat(self._fd).st_size

    def close(self) -> None:
        with self._lock:
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None  # type: ignore[assignment]

    # ---- 개행 탐지 (인코딩 인지) ----------------------------------------

    def find_newlines(self, data: bytes) -> list[int]:
        """data 안에서 개행 패턴 시작 오프셋 목록 (unit 정렬된 것만)."""
        nl = self.info.newline
        unit = self.info.unit_size
        out: list[int] = []
        find = data.find
        start = 0
        nlen = len(nl)
        while True:
            i = find(nl, start)
            if i == -1:
                break
            if unit == 1 or i % unit == 0:
                out.append(i)
                start = i + nlen
            else:
                # 미정렬 매치 — 한 바이트만 전진해 정렬된 매치를 다시 탐색
                start = i + 1
        return out

    def count_newlines(self, data: bytes) -> int:
        """data 안의 개행 수. ASCII/UTF-8/CP949는 C레벨 count로 고속."""
        if self.info.unit_size == 1:
            return data.count(self.info.newline)
        return len(self.find_newlines(data))

    def last_newline(self, data: bytes) -> int:
        """data 안의 마지막 (unit 정렬된) 개행 시작 오프셋. 없으면 -1."""
        nl = self.info.newline
        unit = self.info.unit_size
        i = data.rfind(nl)
        if unit == 1:
            return i
        while i != -1 and i % unit != 0:
            i = data.rfind(nl, 0, i)  # i 직전에서 다시 탐색
        return i

    # ---- 라인 디코드 ---------------------------------------------------

    def decode_line(self, raw: bytes) -> tuple[str, bool]:
        """라인 원시 바이트 → (표시 텍스트, 잘림여부).

        후행 개행/CR을 제거하고 코덱으로 디코드한 뒤 max_line_bytes로 클리핑한다.
        """
        nl = self.info.newline
        if raw.endswith(nl):
            raw = raw[: -len(nl)]
        if raw.endswith(self._cr):
            raw = raw[: -len(self._cr)]

        truncated = False
        if len(raw) > self.max_line_bytes:
            clip = self.max_line_bytes
            clip -= clip % self.info.unit_size  # 유닛 경계 정렬
            raw = raw[:clip]
            truncated = True

        text = raw.decode(self.info.codec, errors="replace")
        return text, truncated
