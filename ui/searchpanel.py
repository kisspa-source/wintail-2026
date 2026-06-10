"""검색 결과 패널 — 툴바 필터와 일치하는 줄을 목록으로 보여주고 클릭으로 이동.

klogg/glogg의 filtered view를 본뜬 우측 사이드 패널. 본문은 그대로 두고
일치 줄(줄 번호 + 내용)만 따로 나열한다. 엔진의 FilterScanner(일치 줄 인덱스,
hide 모드·Enter 찾기와 공유)를 그대로 재사용하므로 추가 메모리가 거의 없다.

표시는 PAGE 단위로 끊어 채운다(일치가 수십만이어도 Treeview가 무거워지지 않게).
행 클릭 → App.show_line이 해당 탭의 그 줄로 이동(gotoline 강조). 필터가 바뀌면
결과가 무효이므로 비우고 다시 검색을 안내한다. 크롬 영역 — 고정 크롬 테마.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from engine.events import FilterComplete

PAGE = 1000        # 한 번에 채우는 행 수("더 보기"로 추가)
SNIPPET_CHARS = 200


class SearchResultPanel(ttk.Frame):
    def __init__(self, app, parent):
        super().__init__(parent, padding=(8, 6))
        self.app = app
        self._tab = None     # 검색을 시작한 탭(결과의 소유자)
        self._shown = 0      # Treeview에 올린 행 수
        self._limit = PAGE   # 현재 표시 상한(더 보기로 증가)

        head = ttk.Frame(self)
        head.pack(side="top", fill="x")
        ttk.Label(head, text="검색 결과").pack(side="left")
        ttk.Button(head, text="✕", width=3, command=app.toggle_search_panel).pack(side="right")

        row = ttk.Frame(self)
        row.pack(side="top", fill="x", pady=(8, 2))
        ttk.Button(row, text="현재 필터로 검색", command=self.scan).pack(side="left")

        self.info_var = tk.StringVar(value="툴바 필터에 검색어를 넣고 검색을 누르세요")
        ttk.Label(self, textvariable=self.info_var, anchor="w", wraplength=300).pack(
            side="top", fill="x", pady=(4, 6))

        body = ttk.Frame(self)
        body.pack(side="top", fill="both", expand=True)
        self.tree = ttk.Treeview(body, columns=("line", "text"), show="headings", height=20)
        self.tree.heading("line", text="줄")
        self.tree.heading("text", text="내용")
        self.tree.column("line", width=80, anchor="e", stretch=False)
        self.tree.column("text", width=260)
        vsb = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        self.more_btn = ttk.Button(self, text="더 보기", command=self._more)
        # pack은 결과가 잘릴 때만 — _update_info에서 토글

    # ---- 검색 ------------------------------------------------------------

    def scan(self) -> None:
        tab = self.app.tabs.current()
        if tab is None:
            self.info_var.set("열린 로그 파일이 없습니다")
            return
        if not tab.filter_pattern:
            self.info_var.set("툴바 필터에 검색어를 먼저 입력하세요")
            return
        self._tab = tab
        self._reset_rows()
        tab.engine.start_match_scan()  # 이미 스캔 중/완료면 그대로 재사용
        self._fill_rows()              # 완료된 스캔이면 이벤트가 더 안 오므로 즉시 채움
        self._update_info(done=tab.engine.is_filter_complete())

    def _reset_rows(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self._shown = 0
        self._limit = PAGE

    def _more(self) -> None:
        if self._tab is None:
            return
        self._limit += PAGE
        self._fill_rows()
        self._update_info(done=self._tab.engine.is_filter_complete())

    def _fill_rows(self) -> None:
        eng = self._tab.engine
        count = min(eng.get_filtered_total(), self._limit)
        while self._shown < count:
            n = min(64, count - self._shown)   # 일치 줄 텍스트는 디스크에서 묶어 읽는다
            lines = eng.get_filtered_lines(self._shown, n)
            if not lines:
                break
            for ln in lines:
                self.tree.insert("", "end", iid=str(self._shown),
                                 values=(f"{ln.line_no + 1:,}", ln.text[:SNIPPET_CHARS]))
                self._shown += 1

    def _update_info(self, done: bool) -> None:
        if self._tab is None:
            return
        total = self._tab.engine.get_filtered_total()
        state = "완료" if done else "스캔 중…"
        extra = f" (표시 {self._shown:,}건)" if total > self._shown else ""
        self.info_var.set(f"{state} {total:,}건{extra}")
        if total > self._shown and done:
            self.more_btn.pack(side="top", fill="x", pady=(6, 0))
        else:
            self.more_btn.pack_forget()

    # ---- 이벤트/이동/정리 --------------------------------------------------

    def on_scan_event(self, tab, event) -> None:
        """LogTab이 펌프에서 받은 FilterProgress/Complete를 전달한다(점진 채움)."""
        if tab is not self._tab:
            return
        self._fill_rows()
        self._update_info(done=isinstance(event, FilterComplete))

    def on_filter_changed(self, tab) -> None:
        """필터가 바뀌면 기존 결과(이전 패턴 기준)는 무효."""
        if tab is self._tab:
            self._tab = None
            self._reset_rows()
            self.more_btn.pack_forget()
            self.info_var.set("필터가 바뀌었습니다 — 다시 검색하세요")

    def _on_select(self, event=None) -> None:
        sel = self.tree.selection()
        if not sel or self._tab is None:
            return
        line = self._tab.engine.filtered_line_no(int(sel[0]))
        if line is None:
            return
        self.app.show_line(self._tab, line)

    def on_tab_closed(self, tab) -> None:
        if tab is self._tab:
            self._tab = None
            self._reset_rows()
            self.more_btn.pack_forget()
            self.info_var.set("탭이 닫혔습니다 — 다시 검색하세요")

    def close(self) -> None:
        self.destroy()
