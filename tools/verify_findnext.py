"""실 창에서 highlight Enter 찾기 + 개수 표시 + 현재 일치 줄 강조를 검증."""

import os
import sys
import tempfile
import time
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import wintail  # noqa: E402


def main() -> int:
    # ERROR가 0,10,20,30,40,50 줄 → 6건
    data = b"".join((b"ERROR %d\n" % i) if i % 10 == 0 else (b"ok %d\n" % i) for i in range(60))
    fd, path = tempfile.mkstemp(suffix=".log")
    os.write(fd, data)
    os.close(fd)

    root = tk.Tk()
    root.geometry("700x320+120+120")
    app = wintail.App(root)
    wintail.cfg.save = lambda *a, **k: None
    app.open_file(path)
    root.deiconify(); root.update_idletasks(); root.update()
    tab = app.tabs.current()
    for _ in range(300):
        app._pump_tick(); root.update()
        if tab.engine.is_index_complete():
            break
    tab.set_live(False)
    tab.model.set_top(0)
    tab.render(); root.update()

    app.filter_var.set("ERROR")
    app._apply_filter_now()
    root.update()

    cursors = []
    for _ in range(3):                       # Enter x3 → 0,10,20
        app._on_filter_enter(forward=True)
        root.update_idletasks(); root.update()
        cursors.append(tab._match_cursor)

    for _ in range(400):                     # 스캔 완료 대기(개수 확정)
        app._pump_tick(); root.update()
        if tab.engine.is_filter_complete():
            break
        time.sleep(0.005)
    tab.render(); root.update()              # 라벨/강조 최종 반영

    content = tab.view.content
    cur = content.tag_ranges("curmatch")
    cur_text = content.get(cur[0], cur[1]) if cur else None
    label = app.match_var.get()

    print("cursors:", cursors)
    print("match label:", repr(label))
    print("curmatch line:", repr(cur_text))

    checks = {
        "커서 0,10,20": cursors == [0, 10, 20],
        "개수 라벨 3/6": label == "3/6",
        "현재 줄 강조=ERROR 20": cur_text == "ERROR 20",
    }
    for name, ok in checks.items():
        print(f"  [{'OK' if ok else 'FAIL'}] {name}")
    ok_all = all(checks.values())

    for t in app.tabs.all():
        t.close()
    root.destroy()
    try:
        os.remove(path)
    except OSError:
        pass
    print("COUNT + CURRENT-HIGHLIGHT", "OK" if ok_all else "FAIL")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
