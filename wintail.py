"""wintail-2026 — 경량 Windows 로그 뷰어 (원조 WinTail 레퍼런스).

설치 없음 · 단일 EXE · 즉시 실행 · 실시간 Tail · 멀티 탭 · UTF-8/CP949 ·
ERROR 레벨 색상 · Regex 필터(숨김/하이라이트) · JSON Pretty · Dark Mode ·
로그 로테이션 감지. 5GB+ 파일도 전체를 메모리에 올리지 않고 가시 영역만 렌더링한다.
"""

from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk

from engine.encoding import supported_codecs
from ui import config as cfg
from ui.bridge import EventPump
from ui.highlight import HighlightRules, LevelClassifier
from ui.searchpanel import SearchResultPanel
from ui.slowpanel import SlowQueryPanel
from ui.style import apply_combobox_popup, apply_style
from ui.tabs import TabManager
from ui.theme import get_theme, resolve_name, theme_names
from ui.toast import show_toast

FONT_CANDIDATES = ["D2Coding", "Sarasa Mono K", "NanumGothicCoding", "Consolas", "Malgun Gothic", "Courier New"]
FILTER_DEBOUNCE_MS = 300
FONT_SIZE_MIN, FONT_SIZE_MAX = 6, 40
CHROME_THEME = "Light+"  # 크롬(메뉴/툴바/버튼/상태바)은 항상 이 테마로 고정


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.config = cfg.load()
        self.theme_name = resolve_name(self.config.get("theme"))
        self.theme = get_theme(self.theme_name)   # 컨텐츠(본문) 테마
        self.chrome = get_theme(CHROME_THEME)      # 크롬은 고정
        self.style = ttk.Style(root)
        self._menus: list[tk.Menu] = []
        self.classifier = LevelClassifier(self.config.get("level_rules"))
        self.rules = HighlightRules(self.config.get("highlight_rules"))
        self._font_family = self._resolve_font()
        self._font_size = self._clamp_size(self.config.get("font_size", 11))
        self.font = tkfont.Font(family=self._font_family, size=self._font_size)
        self.font_tuple = (self._font_family, self._font_size)
        self._wrap = bool(self.config.get("wrap", False))
        self._filter_after = None
        self._toast = None
        self._slow_panel = None
        self._search_panel = None

        root.title("wintail-2026")
        root.geometry("1100x720")
        self._build_menu()      # 커스텀 메뉴바(최상단)
        self._build_toolbar()
        # 본문 컨테이너 — 노트북 + (토글되는) 우측 느린 쿼리 패널. 상태바는 이
        # 컨테이너 아래에 깔려 패널이 열려도 전체 폭을 유지한다.
        self._center = ttk.Frame(root)
        self._center.pack(fill="both", expand=True)
        self.tabs = TabManager(self, self._center)
        self.tabs.notebook.pack(side="left", fill="both", expand=True)
        self._build_statusbar()
        self._apply_theme_chrome()

        self.pump = EventPump(root, self._pump_tick, interval_ms=40)
        self.pump.start()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---- 폰트/테마 ----------------------------------------------------

    def _resolve_font(self) -> str:
        configured = self.config.get("font_family") or ""
        families = set(tkfont.families())
        if configured and configured in families:
            return configured
        for fam in FONT_CANDIDATES:
            if fam in families:
                return fam
        return "TkFixedFont"

    @staticmethod
    def _clamp_size(size) -> int:
        try:
            size = int(size)
        except (TypeError, ValueError):
            size = 11
        return max(FONT_SIZE_MIN, min(FONT_SIZE_MAX, size))

    def _on_wrap_toggle(self) -> None:
        self._wrap = bool(self.wrap_var.get())
        self.config["wrap"] = self._wrap
        cfg.save(self.config)
        for tab in self.tabs.all():
            tab.view.set_wrap(self._wrap)
            tab.render()

    def _change_font_size(self, delta: int) -> None:
        self._set_font_size(self._font_size + delta)

    def _reset_font_size(self) -> None:
        self._set_font_size(cfg.DEFAULTS["font_size"])

    def _set_font_size(self, size) -> None:
        size = self._clamp_size(size)
        if size == self._font_size:
            return
        self._font_size = size
        self._apply_font()

    def _set_font_family(self, family: str) -> None:
        self._font_family = family
        if hasattr(self, "fontfamily_var"):
            self.fontfamily_var.set(family)
        self._apply_font()

    def _apply_chosen_font(self, family: str, size) -> None:
        self._font_family = family
        self._font_size = self._clamp_size(size)
        if hasattr(self, "fontfamily_var"):
            self.fontfamily_var.set(family)
        self._apply_font()

    def _apply_font(self) -> None:
        # 공유 Font 객체를 바꾸면 모든 탭의 거터/본문이 자동 재레이아웃된다.
        self.font.configure(family=self._font_family, size=self._font_size)
        self.font_tuple = (self._font_family, self._font_size)
        self.config["font_family"] = self._font_family
        self.config["font_size"] = self._font_size
        cfg.save(self.config)
        for tab in self.tabs.all():
            tab.view.recompute_line_px()
            tab._on_resize(max(1, tab.view.visible_lines()))

    def _choose_font_dialog(self) -> None:
        from ui.fontdialog import choose_font
        choose_font(self.root, self.chrome, tkfont.families(),
                    self._font_family, self._font_size, self._apply_chosen_font)

    def _apply_theme_chrome(self) -> None:
        """크롬(메뉴/툴바/버튼/상태바)은 고정 테마로, 선택 테마는 탭 컨텐츠에만 적용."""
        c, t = self.chrome, self.theme
        apply_style(self.style, c)
        apply_combobox_popup(self.root, c)
        self.root.configure(bg=c["bg"])
        for m in self._menus:
            try:
                m.configure(bg=c["control_bg"], fg=c["fg"], activebackground=c["accent"],
                            activeforeground="#ffffff", relief="flat", borderwidth=0)
            except tk.TclError:
                pass
        # 활성 탭만 컨텐츠 색과 이어지게(편집기 느낌), 비활성 탭은 크롬 색.
        self.style.map("TNotebook.Tab",
                       background=[("selected", t["bg"]), ("!selected", c["control_bg"])],
                       foreground=[("selected", t["fg"]), ("!selected", c["fg"])])
        for tab in self.tabs.all():
            tab.apply_theme()

    # ---- 위젯 구성 -----------------------------------------------------

    def _build_toolbar(self) -> None:
        self.toolbar = ttk.Frame(self.root, style="Toolbar.TFrame", padding=(8, 6))
        self.toolbar.pack(side="top", fill="x")
        ttk.Separator(self.root, orient="horizontal").pack(side="top", fill="x")  # 툴바|본문 구분선
        ttk.Button(self.toolbar, text="열기", command=self.open_dialog).pack(side="left", padx=2)
        # 표시만 비운다 — 실제 파일은 건드리지 않으며 보기 메뉴에서 복원 가능.
        ttk.Button(self.toolbar, text="화면 지우기", command=self.clear_display).pack(side="left", padx=2)

        self.follow_var = tk.BooleanVar(value=self.config.get("follow_default", True))
        ttk.Checkbutton(self.toolbar, text="Follow", variable=self.follow_var,
                        command=self._on_follow_toggle).pack(side="left", padx=(8, 4))

        ttk.Label(self.toolbar, text="필터:").pack(side="left", padx=(6, 2))
        self.filter_var = tk.StringVar()
        ent = ttk.Entry(self.toolbar, textvariable=self.filter_var, width=28)
        ent.pack(side="left", padx=2)
        ent.bind("<KeyRelease>", self._on_filter_changed)
        ent.bind("<Return>", lambda e: self._on_filter_enter(forward=True))
        ent.bind("<Shift-Return>", lambda e: self._on_filter_enter(forward=False))

        self.regex_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.toolbar, text="Regex", variable=self.regex_var,
                        command=self._apply_filter_now).pack(side="left", padx=2)
        self.case_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.toolbar, text="Aa", variable=self.case_var,
                        command=self._apply_filter_now).pack(side="left", padx=2)
        self.mode_var = tk.StringVar(value="highlight")
        ttk.Combobox(self.toolbar, textvariable=self.mode_var, width=10, state="readonly",
                     values=["highlight", "hide"]).pack(side="left", padx=2)
        self.mode_var.trace_add("write", lambda *a: self._apply_filter_now())

        # 일치 개수(예: 3/12). highlight 모드에서 Enter 찾기를 쓰면 채워진다.
        self.match_var = tk.StringVar(value="")
        ttk.Label(self.toolbar, textvariable=self.match_var, width=11, anchor="w").pack(side="left", padx=4)

        # 우측: 테마 콤보 + 인코딩 (오른쪽부터 역순으로 pack)
        self.theme_var = tk.StringVar(value=self.theme_name)
        ttk.Combobox(self.toolbar, textvariable=self.theme_var, width=14, state="readonly",
                     values=theme_names()).pack(side="right", padx=2)
        ttk.Label(self.toolbar, text="테마:").pack(side="right", padx=(8, 2))
        self.theme_var.trace_add("write", lambda *a: self._on_theme_selected())

        self.enc_var = tk.StringVar(value="auto")
        ttk.Combobox(self.toolbar, textvariable=self.enc_var, width=11, state="readonly",
                     values=["auto", *supported_codecs()]).pack(side="right", padx=2)
        ttk.Label(self.toolbar, text="인코딩:").pack(side="right", padx=(8, 2))
        self.enc_var.trace_add("write", lambda *a: self._on_encoding_changed())

    def _build_statusbar(self) -> None:
        self.status = ttk.Label(self.root, anchor="w", text="준비됨", style="Status.TLabel")
        self.status.pack(side="bottom", fill="x")

    def _build_menu(self) -> None:
        # 네이티브 tk.Menu 메뉴바는 Windows에서 색을 못 입히므로, 테마 가능한
        # ttk.Menubutton 줄로 직접 만든다(드롭다운은 테마 적용되는 tk.Menu).
        bar = ttk.Frame(self.root, style="Menubar.TFrame", padding=(4, 1))
        bar.pack(side="top", fill="x")
        self._menubar_frame = bar

        file_btn = ttk.Menubutton(bar, text="파일", direction="below", style="Menubar.TMenubutton")
        filemenu = tk.Menu(file_btn, tearoff=0)
        filemenu.add_command(label="열기…  (Ctrl+O)", command=self.open_dialog)
        filemenu.add_command(label="탭 닫기  (Ctrl+W)", command=self.close_tab)
        filemenu.add_separator()
        filemenu.add_command(label="종료", command=self._on_close)
        file_btn["menu"] = filemenu
        file_btn.pack(side="left")

        view_btn = ttk.Menubutton(bar, text="보기", direction="below", style="Menubar.TMenubutton")
        viewmenu = tk.Menu(view_btn, tearoff=0)
        viewmenu.add_command(label="다음 테마", command=self.toggle_theme)
        viewmenu.add_command(label="맨 아래로 (End)", command=self._goto_end_current)
        viewmenu.add_separator()
        viewmenu.add_command(label="화면 지우기  (Ctrl+L)", command=self.clear_display)
        viewmenu.add_command(label="지운 화면 복원", command=self.restore_display)
        viewmenu.add_separator()
        viewmenu.add_command(label="검색 결과 패널", command=self.toggle_search_panel)
        viewmenu.add_command(label="느린 쿼리 찾기", command=self.toggle_slow_panel)
        viewmenu.add_command(label="하이라이트 규칙…", command=self.edit_highlight_rules)
        viewmenu.add_separator()
        viewmenu.add_command(label="북마크 토글  (Ctrl+F2)", command=self.toggle_bookmark)
        viewmenu.add_command(label="다음 북마크  (F2)", command=lambda: self.next_bookmark(True))
        viewmenu.add_command(label="이전 북마크  (Shift+F2)", command=lambda: self.next_bookmark(False))
        viewmenu.add_separator()
        self.wrap_var = tk.BooleanVar(value=self._wrap)
        viewmenu.add_checkbutton(label="자동 줄바꿈", variable=self.wrap_var,
                                 command=self._on_wrap_toggle)
        viewmenu.add_separator()
        viewmenu.add_command(label="글꼴 키우기  (Ctrl++)", command=lambda: self._change_font_size(1))
        viewmenu.add_command(label="글꼴 줄이기  (Ctrl+-)", command=lambda: self._change_font_size(-1))
        viewmenu.add_command(label="기본 크기  (Ctrl+0)", command=self._reset_font_size)
        fontmenu = tk.Menu(viewmenu, tearoff=0)
        self._build_font_menu(fontmenu)
        viewmenu.add_cascade(label="글꼴", menu=fontmenu)
        view_btn["menu"] = viewmenu
        view_btn.pack(side="left")
        ttk.Separator(self.root, orient="horizontal").pack(side="top", fill="x")  # 메뉴|툴바 구분선

        self._menus = [filemenu, viewmenu, fontmenu]

        self.root.bind("<Control-o>", lambda e: self.open_dialog())
        self.root.bind("<Control-w>", lambda e: self.close_tab())
        self.root.bind("<Control-l>", lambda e: self.clear_display())
        self.root.bind("<F2>", lambda e: self.next_bookmark(True))
        self.root.bind("<Shift-F2>", lambda e: self.next_bookmark(False))
        self.root.bind("<Control-F2>", lambda e: self.toggle_bookmark())
        self.root.bind("<Control-equal>", lambda e: self._change_font_size(1))
        self.root.bind("<Control-plus>", lambda e: self._change_font_size(1))
        self.root.bind("<Control-minus>", lambda e: self._change_font_size(-1))
        self.root.bind("<Control-Key-0>", lambda e: self._reset_font_size())

    def _build_font_menu(self, menu: tk.Menu) -> None:
        self.fontfamily_var = tk.StringVar(value=self._font_family)
        families = set(tkfont.families())
        for fam in [f for f in FONT_CANDIDATES if f in families]:
            menu.add_radiobutton(label=fam, value=fam, variable=self.fontfamily_var,
                                 command=lambda f=fam: self._set_font_family(f))
        menu.add_separator()
        menu.add_command(label="모든 글꼴…", command=self._choose_font_dialog)

    # ---- 액션 ----------------------------------------------------------

    def open_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="로그 파일 열기",
            filetypes=[("로그/텍스트", "*.log *.txt *.json *.jsonl *.out"), ("모든 파일", "*.*")],
        )
        if path:
            self.open_file(path)

    def open_file(self, path: str) -> None:
        if not os.path.isfile(path):
            self._open_error(path, "파일을 찾을 수 없습니다")
            return
        try:
            tab = self.tabs.add(path)
        except OSError as e:
            self._open_error(path, str(e))
            return
        cfg.push_recent(self.config, path)
        self.reflect_follow(tab)
        tab.apply_theme()
        tab.render()

    def _open_error(self, path: str, reason: str) -> None:
        msg = f"열 수 없음: {path}\n{reason}"
        self.set_status_message(f"열 수 없음: {path} — {reason}")
        print(f"[wintail] 열 수 없음: {path} — {reason}", file=sys.stderr)
        try:
            messagebox.showerror("파일 열기 실패", msg)
        except tk.TclError:
            pass

    def close_tab(self) -> None:
        cur = self.tabs.current()
        self.tabs.close_current()
        if cur is None:
            return
        for panel in (self._slow_panel, self._search_panel):
            if panel is not None:
                panel.on_tab_closed(cur)

    def toggle_bookmark(self) -> None:
        """현재 탭 캐럿 줄의 북마크 토글 — Ctrl+F2 (거터 클릭과 동일)."""
        tab = self.tabs.current()
        if tab is not None:
            tab.toggle_bookmark_at_caret()

    def next_bookmark(self, forward: bool = True) -> None:
        tab = self.tabs.current()
        if tab is not None:
            tab.goto_next_bookmark(forward)

    def edit_highlight_rules(self) -> None:
        """하이라이트 규칙 편집 다이얼로그 — 변경 즉시 모든 탭에 반영·저장."""
        from ui.ruledialog import RuleDialog
        RuleDialog(self.root, self.chrome, self.config.get("highlight_rules", []),
                   self._apply_highlight_rules)

    def _apply_highlight_rules(self, rules: list[dict]) -> None:
        self.config["highlight_rules"] = rules
        cfg.save(self.config)
        self.rules = HighlightRules(rules)
        for tab in self.tabs.all():
            tab.view.set_rule_colors(self.rules.colors())
            tab.render()

    def toggle_slow_panel(self) -> None:
        """느린 쿼리 패널(우측) 열기/닫기 — 닫으면 진행 중 스캔도 중단한다.

        우측 자리는 하나만 쓴다 — 검색 결과 패널이 열려 있으면 먼저 닫는다."""
        if self._slow_panel is not None:
            self._slow_panel.close()
            self._slow_panel = None
            return
        if self._search_panel is not None:
            self.toggle_search_panel()
        self._slow_panel = SlowQueryPanel(self, self._center)
        self._slow_panel.pack(side="right", fill="y")

    def toggle_search_panel(self) -> None:
        """검색 결과 패널(우측) 열기/닫기 — 느린 쿼리 패널과 자리를 공유한다."""
        if self._search_panel is not None:
            self._search_panel.close()
            self._search_panel = None
            return
        if self._slow_panel is not None:
            self.toggle_slow_panel()
        self._search_panel = SearchResultPanel(self, self._center)
        self._search_panel.pack(side="right", fill="y")

    def on_filter_scan_event(self, tab, event) -> None:
        if self._search_panel is not None:
            self._search_panel.on_scan_event(tab, event)

    def on_filter_applied(self, tab) -> None:
        if self._search_panel is not None:
            self._search_panel.on_filter_changed(tab)

    def on_slow_scan_event(self, tab, event) -> None:
        if self._slow_panel is not None:
            self._slow_panel.on_scan_event(tab, event)

    def show_line(self, tab, line: int) -> None:
        """패널(느린 쿼리/검색 결과) 행 클릭 — 그 탭을 앞으로 가져와 해당 줄로 이동."""
        if tab not in self.tabs.all():
            self.set_status_message("해당 로그 탭이 이미 닫혔습니다")
            return
        self.tabs.notebook.select(tab.view)
        tab.goto_line(line)

    def clear_display(self) -> None:
        """현재 탭 화면 지우기 — 표시만 비우고 실제 파일은 건드리지 않는다."""
        tab = self.tabs.current()
        if tab is not None and tab.clear_display():
            self.set_status_message(
                "화면을 지웠습니다 (파일은 그대로) — 보기 ▸ '지운 화면 복원'으로 되돌릴 수 있습니다")

    def restore_display(self) -> None:
        """화면 지우기 해제 — 숨겼던 이전 내용을 다시 보여준다."""
        tab = self.tabs.current()
        if tab is not None:
            tab.restore_display()

    def toggle_theme(self) -> None:
        """다음 프리셋으로 순환(메뉴/단축키). 콤보 var를 바꾸면 trace가 적용한다."""
        names = theme_names()
        i = names.index(self.theme_name) if self.theme_name in names else 0
        self.theme_var.set(names[(i + 1) % len(names)])

    def _on_theme_selected(self) -> None:
        self._apply_theme_named(self.theme_var.get())

    def _apply_theme_named(self, name: str) -> None:
        name = resolve_name(name)
        if name == self.theme_name:
            return
        self.theme_name = name
        self.theme = get_theme(name)
        self.config["theme"] = name
        cfg.save(self.config)
        self._apply_theme_chrome()

    def _goto_end_current(self) -> None:
        tab = self.tabs.current()
        if tab:
            tab._on_goto("end")

    def _on_follow_toggle(self) -> None:
        tab = self.tabs.current()
        if tab:
            tab.set_live(self.follow_var.get())

    def _on_filter_changed(self, event=None) -> None:
        if self._filter_after is not None:
            self.root.after_cancel(self._filter_after)
        self._filter_after = self.root.after(FILTER_DEBOUNCE_MS, self._apply_filter_now)

    def _filter_differs(self, tab) -> bool:
        return (self.filter_var.get() != tab.filter_pattern
                or self.mode_var.get() != tab.filter_mode
                or self.regex_var.get() != tab.filter_regex
                or self.case_var.get() != tab.filter_ignore_case)

    def _apply_filter_now(self) -> None:
        self._filter_after = None
        tab = self.tabs.current()
        # 실제로 바뀐 경우에만 적용한다. Enter의 KeyRelease가 디바운스를 예약하는데,
        # 텍스트가 그대로인데도 재적용하면 apply_filter가 찾기 커서를 리셋해, 천천히
        # 누르면 첫 일치로 되돌아가는 버그가 생긴다.
        if tab is not None and self._filter_differs(tab):
            tab.apply_filter(self.filter_var.get(), self.mode_var.get(),
                             self.regex_var.get(), self.case_var.get())

    def _on_filter_enter(self, forward: bool = True) -> str:
        """필터창 Enter=다음 일치, Shift+Enter=이전 일치(highlight 모드).

        검색어/옵션이 바뀐 경우에만 먼저 필터를 적용하고, 그 외에는 바로 이동한다
        (매 Enter마다 재적용하면 찾기 커서가 리셋돼 제자리에 머문다)."""
        tab = self.tabs.current()
        if tab is None:
            return "break"
        if self._filter_differs(tab):
            if self._filter_after is not None:
                self.root.after_cancel(self._filter_after)
                self._filter_after = None
            tab.apply_filter(self.filter_var.get(), self.mode_var.get(),
                             self.regex_var.get(), self.case_var.get())
        tab.goto_next_match(forward=forward)
        return "break"

    def _on_encoding_changed(self) -> None:
        tab = self.tabs.current()
        if tab is None:
            return
        enc = self.enc_var.get()
        encoding = None if enc == "auto" else enc
        tab.engine.reopen(encoding=encoding)
        tab.model.set_top(0)
        tab.render()

    # ---- 펌프/상태 -----------------------------------------------------

    def _pump_tick(self) -> None:
        current = self.tabs.current()
        for tab in self.tabs.all():
            events = tab.engine.poll_events()
            if events:
                tab.handle_events(events, active=(tab is current))

    def on_tab_changed(self) -> None:
        tab = self.tabs.current()
        if tab is not None:
            self.follow_var.set(tab.live and tab.auto)
            self.filter_var.set(tab.filter_pattern)
            self.mode_var.set(tab.filter_mode)
            self.regex_var.set(tab.filter_regex)
            self.case_var.set(tab.filter_ignore_case)
            tab.render()

    def reflect_follow(self, tab) -> None:
        # 체크박스 = "지금 바닥에 붙어 따라가는 중"(live and auto).
        # follow_var.set()은 Checkbutton command를 호출하지 않으므로 스크롤로 인한
        # 갱신과 사용자 클릭(_on_follow_toggle)이 깔끔히 구분된다.
        if tab is self.tabs.current():
            self.follow_var.set(tab.live and tab.auto)

    def update_status(self, tab) -> None:
        if tab is self.tabs.current():
            self.status.configure(text=tab.status_text())
            self.match_var.set(tab.match_count_text())

    def set_status_message(self, msg: str) -> None:
        self.status.configure(text=msg)

    def copy_query(self, text: str) -> None:
        """더블클릭으로 고른 쿼리를 클립보드에 복사하고 상태바로 알린다."""
        if not text:
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        except tk.TclError:
            return
        self.set_status_message(f"쿼리 복사됨 ({len(text):,}자)")
        self._show_toast(f"복사됨 ({len(text):,}자)")

    def _show_toast(self, text: str) -> None:
        # 라이브 렌더로 상태바가 덮여도 토스트는 독립 창이라 끝까지 보인다.
        if self._toast is not None:
            try:
                self._toast.destroy()
            except tk.TclError:
                pass
        self._toast = show_toast(self.root, text, self.chrome)

    def _on_close(self) -> None:
        self.pump.stop()
        for tab in self.tabs.all():
            tab.close()
        self.config["font_size"] = self._font_size
        cfg.save(self.config)
        self.root.destroy()


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    root = tk.Tk()
    app = App(root)
    for path in argv:
        app.open_file(path)
    root.mainloop()


if __name__ == "__main__":
    main()
