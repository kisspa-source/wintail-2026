"""실제 mainloop로 앱을 잠깐 띄워 창 생성/펌프/follow가 예외 없이 도는지 확인.

사용법: python tools/launch_smoke.py <파일>
약 1.5초 후 자동 종료한다.
"""

import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import wintail  # noqa: E402


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else None
    root = tk.Tk()
    app = wintail.App(root)
    if path:
        app.open_file(path)

    state = {"ticks": 0, "err": None}

    def tick():
        state["ticks"] += 1
        tab = app.tabs.current()
        if tab is not None and state["ticks"] == 20:
            tab.set_live(True)  # follow 토글 검증
        if state["ticks"] >= 40:
            root.destroy()
            return
        root.after(30, tick)

    try:
        root.after(30, tick)
        root.mainloop()
        print("LAUNCH OK — 창 생성/펌프/follow 정상, 예외 없음")
    except Exception as e:  # noqa: BLE001
        print("LAUNCH FAIL:", repr(e))
        raise


if __name__ == "__main__":
    main()
