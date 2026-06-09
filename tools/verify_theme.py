"""실 창에서 '테마=컨텐츠 전용, 크롬=Light+ 고정' 동작을 검증.

각 테마로 전환하며: 본문/거터/현재일치 색은 선택 테마를 따르고, 크롬(메뉴/툴바/
버튼/상태바/탭바)은 Light+로 고정되는지 확인한다.
"""

import os
import sys
import tempfile
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import wintail  # noqa: E402
from ui.theme import get_theme, theme_names  # noqa: E402


def main() -> int:
    fd, path = tempfile.mkstemp(suffix=".log")
    os.write(fd, b"2026 INFO hello\n2026 ERROR boom\n")
    os.close(fd)

    root = tk.Tk()
    root.geometry("1000x600+100+100")
    app = wintail.App(root)
    wintail.cfg.save = lambda *a, **k: None
    app.open_file(path)
    root.deiconify(); root.update_idletasks(); root.update()
    tab = app.tabs.current()
    light = get_theme(wintail.CHROME_THEME)

    all_ok = True
    for name in theme_names():
        app._apply_theme_named(name)
        root.update_idletasks(); root.update()
        t = get_theme(name)
        s = app.style
        checks = {
            # 컨텐츠는 선택 테마
            "본문 bg=테마 bg": str(tab.view.content.cget("bg")) == t["bg"],
            "거터 fg=테마": str(tab.view.gutter.cget("fg")) == t["gutter_fg"],
            # 크롬은 Light+ 고정
            "크롬 TFrame=Light+ toolbar": s.lookup("TFrame", "background") == light["toolbar_bg"],
            "크롬 메뉴바=Light+ menubar": s.lookup("Menubar.TFrame", "background") == light["menubar_bg"],
            "크롬 상태바=Light+ status": s.lookup("Status.TLabel", "background") == light["status_bg"],
            "크롬 메뉴=Light+ control": str(app._menus[0].cget("bg")) == light["control_bg"],
            "버튼 볼록 유지": str(s.lookup("TButton", "relief")) == "raised",
        }
        ok = all(checks.values())
        all_ok = all_ok and ok
        bad = [k for k, v in checks.items() if not v]
        print(f"[{'OK' if ok else 'FAIL'}] {name}" + ("" if ok else f"  실패:{bad}"))

    for t in app.tabs.all():
        t.close()
    root.destroy()
    try:
        os.remove(path)
    except OSError:
        pass
    print("CONTENT-ONLY-THEME", "OK" if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
