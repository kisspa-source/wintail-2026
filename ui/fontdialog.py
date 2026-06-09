"""'모든 글꼴' 선택 다이얼로그.

choose_font는 설치된 전체 글꼴과 크기를 고르는 소형 모달을 띄우고, '적용' 시
on_apply(family, size)를 호출한다. 미리보기로 즉시 모양을 확인한다.
Tk 의존 — 헤드리스 테스트 대상이 아님(jsonpanel과 동일 방침).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

PREVIEW_TEXT = 'ABCabc 0123 한글 미리보기 {"level":"ERROR"}'


def choose_font(parent, theme: dict, families, current_family: str,
                current_size: int, on_apply) -> tk.Toplevel:
    top = tk.Toplevel(parent)
    top.title("글꼴 선택")
    top.transient(parent)
    top.configure(bg=theme["bg"])

    fam_var = tk.StringVar(value=current_family)
    size_var = tk.StringVar(value=str(current_size))

    tk.Label(top, text="글꼴:", bg=theme["bg"], fg=theme["fg"]).grid(
        row=0, column=0, sticky="w", padx=8, pady=6)
    ttk.Combobox(top, textvariable=fam_var, values=sorted(families), width=34,
                 state="readonly").grid(row=0, column=1, sticky="ew", padx=8, pady=6)

    tk.Label(top, text="크기:", bg=theme["bg"], fg=theme["fg"]).grid(
        row=1, column=0, sticky="w", padx=8, pady=6)
    ttk.Spinbox(top, from_=6, to=40, textvariable=size_var, width=6).grid(
        row=1, column=1, sticky="w", padx=8, pady=6)

    preview = tk.Label(top, text=PREVIEW_TEXT, anchor="w", width=40,
                       bg=theme["bg"], fg=theme["fg"])
    preview.grid(row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=8)

    def refresh(*_):
        try:
            preview.configure(font=(fam_var.get(), int(size_var.get())))
        except (tk.TclError, ValueError):
            pass

    fam_var.trace_add("write", refresh)
    size_var.trace_add("write", refresh)
    refresh()

    def apply_and_close():
        try:
            size = int(size_var.get())
        except (tk.TclError, ValueError):
            size = current_size
        on_apply(fam_var.get(), size)
        top.destroy()

    btns = tk.Frame(top, bg=theme["bg"])
    btns.grid(row=3, column=0, columnspan=2, sticky="e", padx=8, pady=6)
    ttk.Button(btns, text="적용", command=apply_and_close).pack(side="right", padx=4)
    ttk.Button(btns, text="취소", command=top.destroy).pack(side="right")

    top.columnconfigure(1, weight=1)
    top.bind("<Return>", lambda e: apply_and_close())
    top.bind("<Escape>", lambda e: top.destroy())
    return top
