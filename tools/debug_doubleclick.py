"""멀티라인 쿼리 더블클릭의 전체 체인을 실 창에서 검증.

_on_double(좌표 파싱) → cb_dblclick → LogTab._on_dblclick(엔진 윈도우) → 복사까지.
Windows Tk는 <Double-Button-1> 합성이 안 되므로 bbox에서 얻은 실제 픽셀로 _on_double을
직접 호출한다(이벤트 전달 이후의 전 구간을 그대로 탄다).
"""

import os
import sys
import tempfile
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import wintail  # noqa: E402


def main() -> int:
    lines = ["2026-06-09 INFO before",
             "2026-06-09 DEBUG Query:{",
             "    SELECT id, name",
             "    FROM users",
             "    WHERE id = 42",
             "}[END]",
             "2026-06-09 INFO after"]
    fd, path = tempfile.mkstemp(suffix=".log")
    os.write(fd, ("\n".join(lines) + "\n").encode("utf-8"))
    os.close(fd)

    root = tk.Tk()
    root.geometry("900x500+120+120")
    app = wintail.App(root)
    wintail.cfg.save = lambda *a, **k: None
    app.open_file(path)
    root.deiconify()
    root.update_idletasks(); root.update()
    tab = app.tabs.current()
    for _ in range(300):
        app._pump_tick(); root.update()
        if tab.engine.is_index_complete():
            break
    tab.model.set_top(0); tab.render()
    root.update_idletasks(); root.update()

    content = tab.view.content
    # 파일 3번째 줄("    SELECT id, name") = render line 3 의 한 픽셀
    bbox = content.bbox("3.8")
    print("bbox(3.8):", bbox)
    px, py = (bbox[0] + 1, bbox[1] + 1) if bbox else (60, 40)

    ev = type("E", (), {"x": px, "y": py})()
    tab.view._on_double(ev)  # 실제 바인딩 핸들러
    root.update_idletasks(); root.update()

    try:
        clip = root.clipboard_get()
    except tk.TclError:
        clip = "<empty>"
    expected = "SELECT id, name\n    FROM users\n    WHERE id = 42"
    print("clipboard:", repr(clip))
    print("status:", repr(app.status.cget("text")))
    ok = clip == expected

    # 토스트: 더블클릭 직후 떠 있고, 잠시 후 자동 소멸해야 한다
    toast_shown = app._toast is not None and app._toast.winfo_exists()
    print("toast shown:", toast_shown)
    import time
    for _ in range(600):
        root.update()
        if app._toast is None or not app._toast.winfo_exists():
            break
        time.sleep(0.005)
    toast_gone = app._toast is None or not app._toast.winfo_exists()
    print("toast auto-dismissed:", toast_gone)
    ok = ok and toast_shown and toast_gone
    print("MULTILINE COPY + TOAST", "OK" if ok else "FAIL")

    for t in app.tabs.all():
        t.close()
    root.destroy()
    try:
        os.remove(path)
    except OSError:
        pass
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
