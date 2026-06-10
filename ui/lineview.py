"""LineView — 가상 스크롤 표시 위젯 (거터 + 본문 Text + 커스텀 스크롤바).

본문 Text에는 항상 화면에 보이는 만큼만 들어간다. 세로 스크롤바는 Text.yview가
아니라 우리 콜백에 연결되어 ViewportModel을 구동한다. 본문은 편집 불가지만
선택/복사/탐색은 가능한 read-only 패턴이다.

LogTab이 콜백(cb_line/cb_page/cb_goto/cb_moveto/cb_resize/cb_zoom/cb_dblclick)을
설정해 스크롤/리사이즈/확대/더블클릭 의도를 받는다.
"""

from __future__ import annotations

import tkinter as tk
import unicodedata

WHEEL_LINES = 3  # 휠 한 칸당 스크롤 줄 수


def _display_width(text: str) -> int:
    """고정폭 기준 표시 칸 수(와이드 문자=2, 탭은 8칸 정렬)."""
    w = 0
    for ch in text:
        if ch == "\t":
            w += 8 - (w % 8)
        elif unicodedata.east_asian_width(ch) in ("W", "F"):
            w += 2
        else:
            w += 1
    return w


def estimate_wrapped_rows(text: str, cols: int) -> int:
    """폭 cols(칸)에서 text가 차지할 표시행 수 추정(고정폭, char-wrap 기준 하한)."""
    if cols <= 0:
        return 1
    return max(1, (_display_width(text) + cols - 1) // cols)


class LineView(tk.Frame):
    def __init__(self, parent, font, theme: dict):
        super().__init__(parent)
        self.font = font
        self._line_px = max(1, font.metrics("linespace"))
        self._last_visible = 0
        self._wrap = False

        self.gutter = tk.Text(
            self, width=6, padx=6, wrap="none", font=font, takefocus=0,
            borderwidth=0, highlightthickness=0, cursor="arrow",
        )
        self.content = tk.Text(
            self, wrap="none", font=font, borderwidth=0, highlightthickness=0,
            insertwidth=0, undo=False,
        )
        self.vbar = tk.Scrollbar(self, orient="vertical", command=self._on_vbar)
        self.hbar = tk.Scrollbar(self, orient="horizontal", command=self.content.xview)
        self.content.configure(xscrollcommand=self.hbar.set)

        self.gutter.grid(row=0, column=0, sticky="ns")
        self.content.grid(row=0, column=1, sticky="nsew")
        self.vbar.grid(row=0, column=2, sticky="ns")
        self.hbar.grid(row=1, column=1, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.gutter.configure(state="disabled")

        # 콜백 (LogTab이 설정)
        self.cb_line = lambda d: None
        self.cb_page = lambda d: None
        self.cb_goto = lambda w: None
        self.cb_moveto = lambda f: None
        self.cb_resize = lambda n: None
        self.cb_zoom = lambda d: None
        self.cb_dblclick = lambda line, col: None  # (render_line, col) — LogTab이 처리
        self.cb_gutter = lambda line: None  # 거터 클릭(render_line) — 북마크 토글

        self._bind_events()
        self.apply_theme(theme, {})

    # ---- 이벤트 바인딩 -------------------------------------------------

    def _bind_events(self) -> None:
        self.content.bind("<Key>", self._on_key)
        self.content.bind("<MouseWheel>", self._on_wheel)
        self.gutter.bind("<MouseWheel>", self._on_wheel)
        self.content.bind("<Configure>", self._on_configure)
        self.content.bind("<Double-Button-1>", self._on_double)
        self.gutter.bind("<Button-1>", self._on_gutter_click)

    def _on_key(self, e):
        k = e.keysym
        ctrl = bool(e.state & 0x4)
        if k == "Prior":
            self.cb_page(-1); return "break"
        if k == "Next":
            self.cb_page(1); return "break"
        if k == "Up":
            self.cb_line(-1); return "break"
        if k == "Down":
            self.cb_line(1); return "break"
        if k == "Home" and not ctrl:
            self.cb_goto("home"); return "break"
        if k == "End" and not ctrl:
            self.cb_goto("end"); return "break"
        if ctrl and k == "Home":
            self.cb_goto("home"); return "break"
        if ctrl and k == "End":
            self.cb_goto("end"); return "break"
        # 복사/전체선택/캐럿 이동은 허용, 나머지 입력은 차단(read-only)
        if ctrl and k.lower() in ("c", "a"):
            return None
        if k in ("Left", "Right", "Shift_L", "Shift_R", "Control_L", "Control_R"):
            return None
        return "break"

    def _on_wheel(self, e):
        if e.state & 0x4:  # Ctrl + 휠: 글꼴 확대/축소
            if e.delta:
                self.cb_zoom(1 if e.delta > 0 else -1)
            return "break"
        steps = int(-e.delta / 120) if e.delta else 0
        if steps:
            self.cb_line(steps * WHEEL_LINES)
        return "break"

    def _on_configure(self, e):
        n = max(1, e.height // self._line_px)
        if n != self._last_visible:
            self._last_visible = n
            self.cb_resize(n)

    def _on_double(self, e):
        # 멀티라인 블록 판단엔 엔진 접근이 필요하므로 좌표만 넘기고 LogTab이 처리한다.
        line, col = self.content.index(f"@{e.x},{e.y}").split(".")
        self.cb_dblclick(int(line), int(col))
        return "break"

    def _on_gutter_click(self, e):
        line = int(self.gutter.index(f"@{e.x},{e.y}").split(".")[0])
        self.cb_gutter(line)
        return "break"

    def mark_bookmarks(self, rows) -> None:
        """북마크 줄들의 거터(줄 번호)를 강조한다(화면 줄 번호 목록).

        렌더마다 LogTab이 다시 호출한다. 줄바꿈 ON이면 거터가 숨겨져 있고
        채워지지도 않으므로 표시하지 않는다(F2 탐색은 그대로 동작)."""
        self.gutter.tag_remove("bm", "1.0", "end")
        if self._wrap:
            return
        for r in rows:
            self.gutter.tag_add("bm", f"{r}.0", f"{r + 1}.0")

    def mark_current(self, render_line) -> None:
        """현재 일치 줄(화면 줄 번호)에 curmatch 강조를 입힌다. None이면 해제.
        렌더마다 LogTab이 다시 불러 스크롤/라이브 갱신에도 유지된다."""
        self.content.tag_remove("curmatch", "1.0", "end")
        if render_line is None:
            return
        last = int(self.content.index("end-1c").split(".")[0])
        if 1 <= render_line <= last:
            self.content.tag_add("curmatch", f"{render_line}.0", f"{render_line}.end")

    def mark_goto(self, render_line) -> None:
        """이동 대상 줄(화면 줄 번호)에 gotoline 강조를 입힌다. None이면 해제.

        sel 태그와 달리 포커스가 없어도 보이고, 렌더마다 LogTab이 다시 불러
        스크롤/라이브 갱신에도 유지된다. 줄 전체 폭(개행 포함)을 칠해 눈에 띈다."""
        self.content.tag_remove("gotoline", "1.0", "end")
        if render_line is None:
            return
        last = int(self.content.index("end-1c").split(".")[0])
        if 1 <= render_line <= last:
            self.content.tag_add("gotoline", f"{render_line}.0", f"{render_line + 1}.0")

    def select_render(self, sl, sc, el, ec) -> None:
        """렌더(화면) 좌표 범위를 선택 표시한다. 줄 번호는 내용 범위로 클램프하고,
        끝 칸으로 "end" 같은 Tk 인덱스 표현도 허용한다. 시각 피드백 전용."""
        last = int(self.content.index("end-1c").split(".")[0])
        sl = max(1, min(int(sl), last))
        el = max(1, min(int(el), last))
        self.content.tag_remove("sel", "1.0", "end")
        self.content.tag_add("sel", f"{sl}.{sc}", f"{el}.{ec}")

    def _on_vbar(self, action, *args):
        if action == "moveto":
            self.cb_moveto(float(args[0]))
        elif action == "scroll":
            n = int(args[0])
            what = args[1] if len(args) > 1 else "units"
            if what == "pages":
                self.cb_page(n)
            else:
                self.cb_line(n * WHEEL_LINES)

    # ---- 폰트/줄바꿈 ---------------------------------------------------

    def recompute_line_px(self) -> None:
        """폰트가 바뀐 뒤 행 높이를 다시 잰다. 다음 가시 줄 수 계산을 강제한다."""
        self._line_px = max(1, self.font.metrics("linespace"))
        self._last_visible = 0

    def estimate_display_rows(self, text: str) -> int:
        """현재 폭/폰트에서 text의 표시행 수 추정(줄바꿈 OFF면 항상 1).
        가운데 정렬 계산용 — 정확한 동기 조회(느림) 대신 순수 계산."""
        if not self._wrap:
            return 1
        charw = max(1, self.font.measure("0"))
        cols = max(1, (self.content.winfo_width() - 4) // charw)
        return estimate_wrapped_rows(text, cols)

    def set_wrap(self, on: bool) -> None:
        """자동 줄바꿈 토글.

        줄바꿈 ON이면 가로 스크롤바와 줄번호 거터를 숨긴다. 거터를 접힌 표시행에
        맞춰 정렬하려면 매 렌더마다 Tk에 표시행 레이아웃을 동기 조회해야 하는데,
        이것이 스크롤을 수백 배 느리게 만들었다(렌더 ~1.5ms → ~330ms). 거터를
        숨겨 그 조회를 통째로 제거한다 — 현재 줄 번호는 상태바가 보여준다.
        """
        self._wrap = on
        self.content.configure(wrap="word" if on else "none")
        if on:
            self.hbar.grid_remove()
            self.gutter.grid_remove()
        else:
            self.hbar.grid()
            self.gutter.grid()

    # ---- 표시 ----------------------------------------------------------

    def visible_lines(self) -> int:
        h = self.content.winfo_height()
        return max(1, h // self._line_px) if h > 1 else 1

    def set_scroll(self, first: float, last: float) -> None:
        self.vbar.set(first, last)

    def set_rule_colors(self, colors: list[str]) -> None:
        """사용자 하이라이트 규칙 태그(hlr<i>)를 규칙 색 목록으로 다시 만든다."""
        for name in self.content.tag_names():
            if name.startswith("hlr"):
                self.content.tag_delete(name)
        for i, color in enumerate(colors):
            try:
                self.content.tag_configure(f"hlr{i}", background=color)
            except tk.TclError:
                pass  # 잘못된 색 문자열은 건너뛴다
        # 필터 일치/이동/현재 일치 강조가 규칙 배경 위에 보이도록 우선순위 유지
        for t in ("match", "gotoline", "curmatch"):
            self.content.tag_raise(t)

    def render(self, lines, classifier, match_spans, rule_spans=None) -> None:
        body = "\n".join(ln.text for ln in lines)
        self.content.delete("1.0", "end")
        self.content.insert("1.0", body)

        # 줄바꿈 ON이면 거터는 숨겨져 있다 — 표시행 조회를 피하려 채우지 않는다.
        if not self._wrap:
            max_no = max((ln.line_no for ln in lines if ln.line_no >= 0), default=0)
            self.gutter.configure(width=max(5, len(str(max_no + 1)) + 1))
            nums = "\n".join(str(ln.line_no + 1) if ln.line_no >= 0 else "" for ln in lines)
            self.gutter.configure(state="normal")
            self.gutter.delete("1.0", "end")
            self.gutter.insert("1.0", nums)
            self.gutter.configure(state="disabled")

        for i, ln in enumerate(lines, start=1):
            lvl = classifier.classify(ln.text)
            if lvl is not None:
                self.content.tag_add(f"lvl_{lvl['name']}", f"{i}.0", f"{i}.end")
            if rule_spans is not None:
                for (ri, s, e) in rule_spans(ln.text):
                    self.content.tag_add(f"hlr{ri}", f"{i}.{s}", f"{i}.{e}")
            for (s, e) in match_spans(ln.text):
                self.content.tag_add("match", f"{i}.{s}", f"{i}.{e}")

    # ---- 테마 ----------------------------------------------------------

    def apply_theme(self, theme: dict, level_colors: dict) -> None:
        self.configure(bg=theme["bg"])  # 컨테이너도 본문색으로(가장자리 이질감 제거)
        for sb in (self.vbar, self.hbar):  # 컨텐츠 스크롤바도 컨텐츠 테마색으로
            try:
                sb.configure(bg=theme["control_bg"], troughcolor=theme["gutter_bg"],
                             activebackground=theme["accent"], highlightthickness=0,
                             borderwidth=0)
            except tk.TclError:
                pass
        for w in (self.content, self.gutter):
            w.configure(bg=theme["bg"], fg=theme["fg"], insertbackground=theme["cursor"],
                        selectbackground=theme["select_bg"])
        self.gutter.configure(bg=theme["gutter_bg"], fg=theme["gutter_fg"])
        self.gutter.tag_configure("bm", background=theme["accent"], foreground="#ffffff")
        self.content.tag_configure("match", background=theme["match_bg"])
        self.content.tag_configure("curmatch", background=theme["current_match_bg"])
        self.content.tag_configure("gotoline", background=theme["select_bg"])
        for name, color in level_colors.items():
            self.content.tag_configure(f"lvl_{name}", foreground=color)
        self.content.tag_raise("gotoline")  # 이동 대상 줄이 일반 match/레벨 위로
        self.content.tag_raise("curmatch")  # 현재 일치 배경이 최상위
