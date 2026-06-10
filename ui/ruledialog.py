"""하이라이트 규칙 편집 다이얼로그 (보기 ▸ 하이라이트 규칙…).

여러 패턴을 각각 다른 배경색으로 칠하는 사용자 규칙을 추가/변경/삭제한다.
변경은 즉시 on_change(rules)로 호출자에 반영(라이브 미리보기)되고, 호출자가
config 저장과 탭 재렌더를 맡는다. Tk 의존 — 스모크 테스트로 검증.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, ttk

# 추가 시 순환 제안되는 기본색 — 라이트/다크 본문 모두에서 글자가 읽히는 파스텔
PALETTE = ["#fff2a8", "#ffd6a5", "#caffbf", "#9bf6ff", "#bdb2ff", "#ffc6ff"]


class RuleDialog:
    def __init__(self, parent, theme: dict, rules: list[dict], on_change):
        self.on_change = on_change
        self.rules = [dict(r) for r in rules]  # 사본을 편집하고 변경 때마다 통지
        self.top = tk.Toplevel(parent)
        self.top.title("하이라이트 규칙")
        self.top.transient(parent)
        self.top.configure(bg=theme["bg"])
        self.top.bind("<Escape>", lambda e: self.top.destroy())

        body = ttk.Frame(self.top, padding=10)
        body.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(body, columns=("pattern", "opts"), show="headings", height=8)
        self.tree.heading("pattern", text="패턴")
        self.tree.heading("opts", text="옵션")
        self.tree.column("pattern", width=260)
        self.tree.column("opts", width=110, stretch=False)
        self.tree.grid(row=0, column=0, columnspan=4, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self._load_selected)

        ttk.Label(body, text="패턴").grid(row=1, column=0, sticky="w", pady=(10, 2))
        self.pattern_var = tk.StringVar()
        ent = ttk.Entry(body, textvariable=self.pattern_var, width=34)
        ent.grid(row=1, column=1, sticky="ew", pady=(10, 2), padx=(4, 8))
        ent.bind("<Return>", lambda e: self.add_rule())
        self.regex_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(body, text="Regex", variable=self.regex_var).grid(
            row=1, column=2, sticky="w", pady=(10, 2))
        self.case_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(body, text="대소문자 구분", variable=self.case_var).grid(
            row=1, column=3, sticky="w", pady=(10, 2))

        ttk.Label(body, text="배경색").grid(row=2, column=0, sticky="w", pady=2)
        self._color = PALETTE[len(self.rules) % len(PALETTE)]
        self.swatch = tk.Label(body, text="  미리보기  ", relief="solid", borderwidth=1)
        self.swatch.grid(row=2, column=1, sticky="w", pady=2, padx=(4, 8))
        ttk.Button(body, text="색 선택…", command=self._pick_color).grid(
            row=2, column=2, sticky="w", pady=2)

        btns = ttk.Frame(body)
        btns.grid(row=3, column=0, columnspan=4, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="추가", command=self.add_rule).pack(side="left", padx=4)
        ttk.Button(btns, text="선택 변경", command=self.update_selected).pack(side="left", padx=4)
        ttk.Button(btns, text="선택 삭제", command=self.delete_selected).pack(side="left", padx=4)
        ttk.Button(btns, text="닫기", command=self.top.destroy).pack(side="left", padx=(12, 0))

        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        self._refresh_swatch()
        self._refresh_tree()

    # ---- 내부 ------------------------------------------------------------

    def _refresh_swatch(self) -> None:
        try:
            self.swatch.configure(bg=self._color, fg="#000000")
        except tk.TclError:
            pass

    def _refresh_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(self.rules):
            opts = []
            if r.get("regex"):
                opts.append("Regex")
            opts.append("Aa" if r.get("ignore_case", True) is False else "aA")
            self.tree.insert("", "end", iid=str(i), values=(r.get("pattern", ""), " ".join(opts)),
                             tags=(f"c{i}",))
            try:
                self.tree.tag_configure(f"c{i}", background=r.get("color", "#fff2a8"),
                                        foreground="#000000")
            except tk.TclError:
                pass

    def _selected_index(self) -> int | None:
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _load_selected(self, event=None) -> None:
        i = self._selected_index()
        if i is None or not (0 <= i < len(self.rules)):
            return
        r = self.rules[i]
        self.pattern_var.set(r.get("pattern", ""))
        self.regex_var.set(bool(r.get("regex", False)))
        self.case_var.set(not r.get("ignore_case", True))
        self._color = r.get("color", "#fff2a8")
        self._refresh_swatch()

    def _pick_color(self) -> None:
        _, hexcolor = colorchooser.askcolor(self._color, parent=self.top, title="하이라이트 색")
        if hexcolor:
            self._color = hexcolor
            self._refresh_swatch()

    def _current_fields(self) -> dict | None:
        pattern = self.pattern_var.get().strip()
        if not pattern:
            return None
        return {"pattern": pattern, "color": self._color,
                "regex": bool(self.regex_var.get()),
                "ignore_case": not self.case_var.get()}

    def _emit(self) -> None:
        self._refresh_tree()
        self.on_change([dict(r) for r in self.rules])

    # ---- 동작 ------------------------------------------------------------

    def add_rule(self) -> None:
        r = self._current_fields()
        if r is None:
            return
        self.rules.append(r)
        self._emit()
        self.pattern_var.set("")
        self._color = PALETTE[len(self.rules) % len(PALETTE)]  # 다음 추천색
        self._refresh_swatch()

    def update_selected(self) -> None:
        i = self._selected_index()
        r = self._current_fields()
        if i is None or r is None or not (0 <= i < len(self.rules)):
            return
        self.rules[i] = r
        self._emit()

    def delete_selected(self) -> None:
        i = self._selected_index()
        if i is None or not (0 <= i < len(self.rules)):
            return
        del self.rules[i]
        self._emit()
