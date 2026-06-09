"""줄바꿈 ON에서 '찾은 row'가 화면 가운데(가려지지 않음)에 오는지 검증.

긴 줄이 여러 표시행으로 접히는 좁은 창에서 highlight 찾기로 중간 일치로 이동한 뒤,
그 줄의 화면 y픽셀이 뷰포트 안(특히 하단에 가려지지 않음)인지 확인한다.
"""

import os
import sys
import tempfile
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import wintail  # noqa: E402


def main() -> int:
    rows = []
    for i in range(1000):  # 뷰포트보다 충분히 큰 파일(실제 로그처럼)
        tag = "ERROR" if i % 100 == 0 else "ok"
        rows.append(f"{i:04d} {tag} " + ("payload-%d " % i) * 30)  # 길어서 접힘
    fd, path = tempfile.mkstemp(suffix=".log")
    os.write(fd, ("\n".join(rows) + "\n").encode("utf-8"))
    os.close(fd)

    root = tk.Tk()
    root.geometry("520x260+120+120")
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
    tab.view.set_wrap(True)               # 줄바꿈 ON
    tab.model.set_top(0)
    tab.render(); root.update_idletasks(); root.update()

    app.filter_var.set("ERROR")
    app._apply_filter_now(); root.update()
    for _ in range(6):                    # ERROR at 0,100,... → 중간(500)으로
        app._on_filter_enter(forward=True)
        root.update_idletasks(); root.update()
    cursor = tab._match_cursor

    content = tab.view.content
    h = content.winfo_height()
    line_px = tab.view._line_px
    rl = cursor - tab.model.top_line + 1
    info = content.dlineinfo(f"{rl}.0")
    y = info[1] if info else None

    # --- 추정 진단 ---
    cw = content.winfo_width()
    charw = tab.view.font.measure("0")
    cols = max(1, (cw - 4) // charw)
    print(f"content_w={cw} charw={charw} cols={cols}")

    print(f"cursor={cursor} top={tab.model.top_line} viewport={tab.model.viewport_lines}")
    print(f"widget_h={h} line_px={line_px} target_y={y}")
    if y is not None:
        print(f"  y/h = {y / h:.2f}")

    checks = {
        "현재 줄 = 500": cursor == 500,
        "대상 줄 화면에 보임(dlineinfo 존재)": y is not None,
        "하단에 가려지지 않음(y <= 0.75*h)": (y is not None and y <= 0.75 * h),
        "맨 위 붙지 않음(중앙 근처, y >= 0.1*h)": (y is not None and y >= 0.10 * h),
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
    print("WRAP-CENTER", "OK" if ok_all else "FAIL")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
