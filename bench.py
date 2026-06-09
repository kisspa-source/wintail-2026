"""대용량 파일 성능/메모리 벤치 (개발용).

사용법:  python bench.py [크기MB]
- 합성 로그 생성 → 즉시 tail 표시 지연 / 전체 인덱싱 시간·처리량 / 프로세스 RSS /
  임의 라인 접근 지연을 측정한다.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import sys
import tempfile
import time

from engine.logengine import LogEngine


def rss_bytes() -> int:
    class PMC(ctypes.Structure):
        _fields_ = [
            ("cb", wt.DWORD),
            ("PageFaultCount", wt.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    k32 = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi
    k32.GetCurrentProcess.restype = wt.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(PMC), wt.DWORD]
    psapi.GetProcessMemoryInfo.restype = wt.BOOL
    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    ok = psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
    return pmc.WorkingSetSize if ok else 0


def make_log(path: str, target_mb: int) -> int:
    target = target_mb * 1024 * 1024
    block = "".join(
        f"2026-06-08 12:00:{i % 60:02d} {'ERROR' if i % 7 == 0 else 'INFO'} "
        f"모듈{i % 5} 메시지 번호 {i} 한국어 로그 라인 테스트\n"
        for i in range(2000)
    ).encode("utf-8")
    written = 0
    with open(path, "wb") as f:
        while written < target:
            f.write(block)
            written += len(block)
    return written


def main() -> None:
    mb = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    path = os.path.join(tempfile.gettempdir(), f"wintail_bench_{mb}mb.log")
    base_rss = rss_bytes()
    if not os.path.exists(path) or os.path.getsize(path) < mb * 1024 * 1024 * 0.9:
        print(f"[gen] {mb}MB 로그 생성 중: {path}")
        t = time.perf_counter()
        size = make_log(path, mb)
        print(f"[gen] {size/1e6:.0f} MB, {time.perf_counter()-t:.1f}s")
    size = os.path.getsize(path)

    eng = LogEngine()
    t0 = time.perf_counter()
    eng.open(path)
    probe = eng.get_tail_probe(40)
    t_probe = time.perf_counter() - t0
    print(f"[open] 즉시 tail 표시: {t_probe*1000:.1f} ms ({len(probe)}줄)")

    while not eng.is_index_complete():
        time.sleep(0.01)
    t_index = time.perf_counter() - t0
    total = eng.get_total_lines()
    print(f"[index] 완료: {t_index:.2f}s, {total:,}줄, "
          f"처리량 {size/1e6/t_index:.0f} MB/s")

    mid = total // 2
    t = time.perf_counter()
    lines = eng.get_lines(mid, 50)
    t_rand = (time.perf_counter() - t) * 1000
    print(f"[random] 중앙 라인 {mid:,} 접근: {t_rand:.2f} ms ({len(lines)}줄)")

    t = time.perf_counter()
    eng.set_filter("ERROR", mode="hide")
    while not eng.is_filter_complete():
        time.sleep(0.01)
    t_filter = time.perf_counter() - t
    print(f"[filter] hide 'ERROR': {t_filter:.2f}s, {eng.get_filtered_total():,} 매치")

    peak_rss = rss_bytes()
    print(f"[memory] 프로세스 RSS: {peak_rss/1e6:.1f} MB "
          f"(시작 {base_rss/1e6:.1f} MB, 파일 {size/1e6:.0f} MB) — 인덱스/엔진 순증 "
          f"{(peak_rss-base_rss)/1e6:.1f} MB")
    eng.close()


if __name__ == "__main__":
    main()
