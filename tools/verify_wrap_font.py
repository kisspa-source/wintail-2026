"""실 창에서 자동 줄바꿈 + 폰트 변경 동작/성능을 검증한다.

수정 후 기대:
  - wrap ON: content wrap=word, 줄번호 거터 숨김(grid 비관리), 가로 스크롤바 숨김.
  - 성능: 줄바꿈 렌더가 표시행을 조회하지 않아 비줄바꿈 렌더와 비슷한 속도
    (예전엔 ~222배 느렸다). render ON/OFF 비율이 작아야 한다.
  - 폰트 크기 변경이 행 높이/ font_tuple에 반영.
  - wrap OFF: 거터/스크롤바 복귀.
"""

import os
import sys
import tempfile
import time
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import wintail  # noqa: E402


def _t(fn, n):
    fn()
    s = time.perf_counter()
    for _ in range(n):
        fn()
    return (time.perf_counter() - s) / n * 1000


def main() -> int:
    rows = []
    for i in range(5000):
        rows.append(f"{i:05d} INFO short" if i % 3 == 0
                    else f"{i:05d} ERROR " + ("payload=%d " % i) * (20 + i % 40))
    fd, path = tempfile.mkstemp(suffix=".log")
    os.write(fd, ("\n".join(rows) + "\n").encode("utf-8"))
    os.close(fd)

    root = tk.Tk()
    root.geometry("1100x720")
    app = wintail.App(root)
    wintail.cfg.save = lambda *a, **k: None
    app.open_file(path)
    root.update_idletasks(); root.update()
    tab = app.tabs.current()
    for _ in range(300):
        app._pump_tick(); root.update()
        if tab.engine.is_index_complete():
            break
    tab.model.set_viewport_lines(max(1, tab.view.visible_lines()))
    tab.model.set_top(1000)

    tab.view.set_wrap(False); root.update()
    off = _t(lambda: tab.render(), 30)
    gutter_shown_off = bool(tab.view.gutter.grid_info())

    tab.view.set_wrap(True); root.update()
    on = _t(lambda: tab.render(), 30)
    gutter_hidden_on = not tab.view.gutter.grid_info()
    wrap_word = str(tab.view.content.cget("wrap")) == "word"
    hbar_hidden = not tab.view.hbar.grid_info()

    before_px = tab.view._line_px
    app._set_font_size(24); root.update_idletasks()
    px_grew = tab.view._line_px > before_px
    tuple_ok = app.font_tuple == (app._font_family, 24)

    tab.view.set_wrap(False); root.update()
    gutter_back = bool(tab.view.gutter.grid_info())

    ratio = on / max(off, 1e-9)

    for t in app.tabs.all():
        t.close()
    root.destroy()
    try:
        os.remove(path)
    except OSError:
        pass

    checks = {
        "wrap 옵션=word": wrap_word,
        "wrap ON 거터 숨김": gutter_hidden_on,
        "wrap ON 가로바 숨김": hbar_hidden,
        "기본 거터 표시": gutter_shown_off,
        "wrap OFF 거터 복귀": gutter_back,
        "폰트 행높이 증가": px_grew,
        "font_tuple 갱신": tuple_ok,
        "렌더 ON≈OFF (비율<5)": ratio < 5,
    }
    print(f"render  OFF={off:6.2f} ms   ON={on:6.2f} ms   ratio=x{ratio:.2f}   "
          f"line_px {before_px}->{tab.view._line_px}")
    for name, ok in checks.items():
        print(f"  [{'OK' if ok else 'FAIL'}] {name}")
    ok_all = all(checks.values())
    print("VERIFY", "OK" if ok_all else "FAIL")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
