"""선택 줄 JSON Pretty.

pretty_json은 한 줄에서 JSON 객체/배열을 추출해 들여쓰기된 문자열로 만든다.
로그 줄 앞에 타임스탬프/레벨 같은 접두사가 있어도 첫 '{' 또는 '['부터 파싱을
시도하고, 뒤따르는 잉여 텍스트는 raw_decode로 무시한다. 한글은 보존한다.
Tk 표시는 show_json_popup이 담당한다.
"""

from __future__ import annotations

import json

_DECODER = json.JSONDecoder()


def pretty_json(text: str) -> str | None:
    text = text.strip()
    if not text:
        return None
    starts = {0}
    for ch in ("{", "["):
        i = text.find(ch)
        if i >= 0:
            starts.add(i)
    for s in sorted(starts):
        candidate = text[s:].lstrip()
        try:
            obj, _ = _DECODER.raw_decode(candidate)
        except ValueError:
            continue
        # JSON Pretty는 객체/배열만 대상으로 한다(접두사의 숫자 등 오인 방지)
        if isinstance(obj, (dict, list)):
            return json.dumps(obj, indent=2, ensure_ascii=False)
    return None


def show_json_popup(parent, text: str, theme: dict[str, str], font: tuple) -> None:
    """선택 줄의 JSON을 팝업 Toplevel에 들여쓰기로 보여준다.

    Tk 의존 — 헤드리스 테스트 대상이 아님. 유효 JSON이 없으면 아무 것도 안 한다.
    """
    import tkinter as tk
    from tkinter import ttk

    pretty = pretty_json(text)
    if pretty is None:
        return
    top = tk.Toplevel(parent)
    top.title("JSON Pretty")
    top.configure(bg=theme["bg"])
    txt = tk.Text(
        top, wrap="none", bg=theme["bg"], fg=theme["fg"],
        insertbackground=theme["cursor"], selectbackground=theme["select_bg"],
        font=font, width=80, height=30, borderwidth=0, highlightthickness=0, padx=8, pady=6,
    )
    txt.insert("1.0", pretty)
    txt.configure(state="disabled")
    yscroll = ttk.Scrollbar(top, orient="vertical", command=txt.yview)
    xscroll = ttk.Scrollbar(top, orient="horizontal", command=txt.xview)
    txt.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
    txt.grid(row=0, column=0, sticky="nsew")
    yscroll.grid(row=0, column=1, sticky="ns")
    xscroll.grid(row=1, column=0, sticky="ew")
    top.rowconfigure(0, weight=1)
    top.columnconfigure(0, weight=1)
    top.bind("<Escape>", lambda e: top.destroy())
