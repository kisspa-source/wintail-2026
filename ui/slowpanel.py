"""느린 쿼리 패널 — 기준 시간(초) 이상 걸린 쿼리 줄을 나열하고 클릭으로 이동.

보기 메뉴로 토글되는 우측 사이드 패널. 엔진의 SlowQueryScanner가 백그라운드로
`Time:<ms>` 패턴을 스캔하고, 결과(줄 번호·실행시간)를 Treeview에 점진적으로
채운다. 행을 클릭하면 App.show_line이 스캔했던 탭의 해당 줄로 이동한다.
크롬 영역이므로 고정 크롬 테마(ttk 스타일)를 따른다.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from engine.events import SlowScanComplete
from ui import config as cfg

MAX_ROWS = 5000  # Treeview 표시 상한 — 이보다 많으면 기준을 높이는 게 맞다


class SlowQueryPanel(ttk.Frame):
    def __init__(self, app, parent):
        super().__init__(parent, padding=(8, 6))
        self.app = app
        self._tab = None   # 스캔을 시작한 탭(결과의 소유자)
        self._shown = 0    # Treeview에 올린 행 수

        head = ttk.Frame(self)
        head.pack(side="top", fill="x")
        ttk.Label(head, text="느린 쿼리 찾기").pack(side="left")
        ttk.Button(head, text="✕", width=3, command=app.toggle_slow_panel).pack(side="right")

        row = ttk.Frame(self)
        row.pack(side="top", fill="x", pady=(8, 2))
        ttk.Label(row, text="기준").pack(side="left")
        self.threshold_var = tk.StringVar(value=str(app.config.get("slow_threshold_s", 1.0)))
        ent = ttk.Entry(row, textvariable=self.threshold_var, width=7, justify="right")
        ent.pack(side="left", padx=4)
        ent.bind("<Return>", lambda e: self.scan())
        ttk.Label(row, text="초 이상").pack(side="left")
        ttk.Button(row, text="검색", command=self.scan).pack(side="left", padx=(8, 0))

        self.info_var = tk.StringVar(value="기준 시간을 정하고 검색을 누르세요")
        ttk.Label(self, textvariable=self.info_var, anchor="w", wraplength=240).pack(
            side="top", fill="x", pady=(4, 6))

        body = ttk.Frame(self)
        body.pack(side="top", fill="both", expand=True)
        self.tree = ttk.Treeview(body, columns=("line", "ms"), show="headings", height=20)
        self.tree.heading("line", text="줄")
        self.tree.heading("ms", text="실행시간")
        self.tree.column("line", width=90, anchor="e", stretch=False)
        self.tree.column("ms", width=110, anchor="e")
        vsb = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

    # ---- 스캔 -----------------------------------------------------------

    def threshold_ms(self) -> int | None:
        """입력값(초)을 ms로. 숫자가 아니거나 음수면 None."""
        try:
            sec = float(self.threshold_var.get().strip().replace(",", ""))
        except ValueError:
            return None
        if sec < 0:
            return None
        return int(round(sec * 1000))

    def scan(self) -> None:
        ms = self.threshold_ms()
        if ms is None:
            self.info_var.set("기준이 올바르지 않습니다 — 숫자(초)를 입력하세요")
            return
        tab = self.app.tabs.current()
        if tab is None:
            self.info_var.set("열린 로그 파일이 없습니다")
            return
        if self._tab is not None and self._tab is not tab and self._tab in self.app.tabs.all():
            self._tab.engine.stop_slow_scan()  # 다른 탭으로 옮기면 이전 스캔 정리
        self._tab = tab
        self.app.config["slow_threshold_s"] = ms / 1000
        cfg.save(self.app.config)
        self._reset_rows()
        tab.engine.start_slow_scan(ms)
        self.info_var.set("스캔 중…")

    def _reset_rows(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self._shown = 0

    def on_scan_event(self, tab, event) -> None:
        """LogTab이 펌프에서 받은 SlowScan 이벤트를 전달한다(점진 채움)."""
        if tab is not self._tab:
            return
        self._fill_rows()
        total = tab.engine.slow_hit_count()
        note = ""
        if total > MAX_ROWS:
            note = f" (표시는 {MAX_ROWS:,}건까지)"
        if tab.engine.slow_scan_capped():
            note += " — 너무 많아 스캔을 멈췄습니다. 기준을 높이세요"
        if isinstance(event, SlowScanComplete):
            self.info_var.set(f"완료: {total:,}건{note}")
        else:
            self.info_var.set(f"스캔 중… {total:,}건{note}")

    def _fill_rows(self) -> None:
        eng = self._tab.engine
        count = min(eng.slow_hit_count(), MAX_ROWS)
        while self._shown < count:
            hit = eng.slow_hit(self._shown)
            if hit is None:
                break
            line, ms = hit
            self.tree.insert("", "end", iid=str(self._shown),
                             values=(f"{line + 1:,}", f"{ms:,} ms"))
            self._shown += 1

    # ---- 이동/정리 -------------------------------------------------------

    def _on_select(self, event=None) -> None:
        sel = self.tree.selection()
        if not sel or self._tab is None:
            return
        hit = self._tab.engine.slow_hit(int(sel[0]))
        if hit is None:
            return
        self.app.show_line(self._tab, hit[0])

    def on_tab_closed(self, tab) -> None:
        """스캔했던 탭이 닫히면 결과를 비운다(엔진은 탭이 닫으며 이미 정지)."""
        if tab is self._tab:
            self._tab = None
            self._reset_rows()
            self.info_var.set("탭이 닫혔습니다 — 다시 검색하세요")

    def close(self) -> None:
        """패널 닫기 — 진행 중 스캔을 중단하고 위젯을 제거한다."""
        if self._tab is not None and self._tab in self.app.tabs.all():
            self._tab.engine.stop_slow_scan()
        self.destroy()
