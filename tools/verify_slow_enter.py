"""실 타이머로 '천천히 Enter' 시나리오 검증.

Enter의 KeyRelease가 거는 디바운스(_on_filter_changed → after 300ms →
_apply_filter_now)가 실제로 발화한 뒤에도 찾기 커서가 유지되고 다음 일치로
계속 이동하는지 확인한다.
"""

import os
import sys
import tempfile
import time
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import wintail  # noqa: E402


def main() -> int:
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
    tab.set_live(False); tab.model.set_top(0); tab.render(); root.update()

    app.filter_var.set("ERROR")
    app._apply_filter_now()
    root.update()

    app._on_filter_enter(forward=True)   # 0
    app._on_filter_enter(forward=True)   # 10
    after_two = tab._match_cursor

    # 느린 Enter 모사: KeyRelease가 디바운스를 실제로 예약하고, 300ms+ 흐른다
    app._on_filter_changed()
    deadline = wintail.FILTER_DEBOUNCE_MS / 1000 + 0.2
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < deadline:
        root.update()
        time.sleep(0.01)
    after_debounce = tab._match_cursor    # 리셋되면 None

    app._on_filter_enter(forward=True)   # 다음 → 20 (버그면 0/10)
    after_next = tab._match_cursor

    print("after two Enters:", after_two)
    print("after debounce fired:", after_debounce)
    print("after next Enter:", after_next)
    checks = {
        "두 번 후 커서 10": after_two == 10,
        "디바운스 후 커서 유지(10)": after_debounce == 10,
        "다음 Enter → 20": after_next == 20,
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
    print("SLOW-ENTER", "OK" if ok_all else "FAIL")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
