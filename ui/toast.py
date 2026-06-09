"""짧게 떴다 사라지는 토스트 알림.

복사 같은 즉시 동작의 피드백용. 테두리 없는 Toplevel을 마우스 포인터 근처에 띄워
페이드 인 → 잠깐 유지 → 페이드 아웃 후 자동 소멸한다. 포커스를 가져가지 않아 입력을
방해하지 않는다. Tk 의존 — 헤드리스 단위테스트 대상은 아니지만, 생성/소멸은 검증한다.
"""

from __future__ import annotations

import tkinter as tk


def show_toast(root, text: str, theme: dict, duration_ms: int = 1100) -> tk.Toplevel:
    top = tk.Toplevel(root)
    top.overrideredirect(True)
    try:
        top.attributes("-topmost", True)
    except tk.TclError:
        pass

    tk.Label(
        top, text=text, bg=theme["status_bg"], fg=theme["status_fg"],
        padx=14, pady=7, bd=0,
    ).pack()

    # 포인터 근처에 배치(방금 클릭한 자리 옆).
    top.geometry(f"+{root.winfo_pointerx() + 14}+{root.winfo_pointery() + 16}")

    def set_alpha(a: float) -> None:
        try:
            top.attributes("-alpha", a)
        except tk.TclError:
            pass

    def destroy() -> None:
        try:
            top.destroy()
        except tk.TclError:
            pass

    set_alpha(0.0)
    for i, a in enumerate((0.5, 0.93)):           # 페이드 인
        top.after(45 * i, lambda a=a: set_alpha(a))
    out = max(0, duration_ms - 240)               # 페이드 아웃 시작
    for i, a in enumerate((0.7, 0.45, 0.2, 0.0)):
        top.after(out + 60 * i, lambda a=a: set_alpha(a))
    top.after(duration_ms, destroy)               # 자동 소멸
    return top
