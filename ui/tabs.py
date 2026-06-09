"""LogTab(탭별 컨트롤러) + TabManager(ttk.Notebook).

각 탭은 독립 LogEngine + LineView + ViewportModel + follow/filter 상태를 소유한다.
엔진 이벤트는 App의 단일 펌프가 각 탭으로 라우팅하고, 활성 탭만 다시 그린다.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

from engine.events import (
    Appended,
    EncodingDetected,
    FileError,
    FilterComplete,
    FilterProgress,
    IndexComplete,
    IndexProgress,
    Opened,
    Truncated,
)
from engine.logengine import LogEngine
from ui.jsonpanel import pretty_json, show_json_popup
from ui.lineview import LineView
from ui.queryspan import find_brace_block
from ui.viewport import ViewportModel

QUERY_WINDOW = 2000  # 더블클릭 시 위/아래로 읽어 블록을 찾는 최대 줄 수


class LogTab:
    def __init__(self, app, path: str):
        self.app = app
        self.path = path
        self.live = bool(app.config.get("follow_default", True))
        self.auto = self.live
        self.encoding_label = "?"
        self.filter_pattern = ""
        self.filter_mode = "highlight"
        self.filter_regex = False
        self.filter_ignore_case = False
        self._status_msg = ""
        self._match_cursor = None  # 마지막으로 이동한 일치 줄(Enter 찾기용)

        # 위젯을 만들기 전에 파일부터 연다 — 실패하면(없는 파일/권한 등) 예외가
        # 위로 전파되고 위젯/엔진 자원이 남지 않는다.
        self.engine = LogEngine()
        encoding = app.config.get("encoding_default") or None
        self.engine.open(path, encoding=encoding, follow=self.live)

        self.view = LineView(app.tabs.notebook, app.font, app.theme)
        self.view.set_wrap(getattr(app, "_wrap", False))
        self.model = ViewportModel()
        self._wire_view()
        self.model.set_viewport_lines(max(1, self.view.visible_lines()))
        self._initial_probe()

    # ---- 뷰 콜백 연결 --------------------------------------------------

    def _wire_view(self) -> None:
        v = self.view
        v.cb_line = self._on_line
        v.cb_page = self._on_page
        v.cb_goto = self._on_goto
        v.cb_moveto = self._on_moveto
        v.cb_resize = self._on_resize
        v.cb_zoom = self._on_zoom
        v.cb_dblclick = self._on_dblclick

    def _initial_probe(self) -> None:
        n = max(1, self.model.viewport_lines)
        probe = self.engine.get_tail_probe(n)
        if probe:
            self.view.render(probe, self.app.classifier, self.engine.match_spans)

    # ---- 렌더링 --------------------------------------------------------

    def _is_hide(self) -> bool:
        return self.filter_mode == "hide" and self.engine.filter_mode() == "hide"

    def _source_total(self) -> int:
        return self.engine.get_filtered_total() if self._is_hide() else self.engine.get_total_lines()

    def _fetch(self, top: int, n: int):
        if self._is_hide():
            return self.engine.get_filtered_lines(top, n)
        lines = self.engine.get_lines(top, n)
        if not lines and self.engine.get_total_lines() == 0 and not self.engine.is_index_complete():
            return self.engine.get_tail_probe(n)
        return lines

    def render(self) -> None:
        self.model.set_total(self._source_total())
        lines = self._fetch(self.model.top_line, self.model.viewport_lines)
        self.view.render(lines, self.app.classifier, self.engine.match_spans)
        self._refresh_current_highlight()
        first, last = self.model.scroll_fractions()
        self.view.set_scroll(first, last)
        self.app.update_status(self)

    def _refresh_current_highlight(self) -> None:
        """현재 일치 줄이 화면에 보이면 curmatch 강조를 다시 입힌다(렌더마다)."""
        if self._match_cursor is None or self._is_hide():
            self.view.mark_current(None)
            return
        rl = self._match_cursor - self.model.top_line + 1
        self.view.mark_current(rl if 1 <= rl <= self.model.viewport_lines else None)

    # ---- 이벤트 처리 ---------------------------------------------------

    def handle_events(self, events: list, active: bool) -> None:
        changed = False
        for e in events:
            if isinstance(e, (Opened, IndexProgress, IndexComplete, Appended, FilterProgress, FilterComplete)):
                changed = True
            elif isinstance(e, Truncated):
                self.model.set_top(0)
                changed = True
            elif isinstance(e, EncodingDetected):
                self.encoding_label = e.label
                changed = True
            elif isinstance(e, FileError):
                self._status_msg = e.message
                changed = True
        if changed:
            self.model.set_total(self._source_total())
            if self.live and self.auto:
                self.model.goto_end()
            if active:
                self.render()

    # ---- 스크롤/입력 콜백 ---------------------------------------------

    def _after_user_scroll(self) -> None:
        # 바닥에 있으면 auto 추적 재개, 위로 올라가면 해제
        self.auto = self.model.at_bottom()
        self.app.reflect_follow(self)
        self.render()

    def _on_line(self, delta: int) -> None:
        self.model.scroll_lines(delta)
        self._after_user_scroll()

    def _on_page(self, delta: int) -> None:
        self.model.page(delta)
        self._after_user_scroll()

    def _on_moveto(self, frac: float) -> None:
        self.model.moveto(frac)
        self._after_user_scroll()

    def _on_goto(self, where: str) -> None:
        if where == "home":
            self.model.set_top(0)
        else:
            self.model.goto_end()
        self._after_user_scroll()

    def _on_resize(self, n: int) -> None:
        self.model.set_viewport_lines(n)
        if self.live and self.auto:
            self.model.goto_end()
        self.render()

    def _on_zoom(self, delta: int) -> None:
        self.app._change_font_size(delta)

    def _on_dblclick(self, render_line: int, col: int) -> None:
        """더블클릭: 클릭 지점을 감싸는 { } 쿼리 블록(여러 줄 가능)을 선택+복사한다.

        멀티라인 블록은 화면 밖까지 걸칠 수 있으므로 클릭 줄을 기준으로 엔진에서
        ±QUERY_WINDOW줄을 읽어(1회성, 즉시 해제) 균형 매칭한다. 못 찾으면 JSON
        팝업으로 폴백하고, 그것도 아니면 상태바로 안내해 무반응을 막는다.
        """
        abs_line = self._abs_file_line(render_line)
        if abs_line is None:
            return
        start = max(0, abs_line - QUERY_WINDOW)
        lines = [ln.text for ln in self.engine.get_lines(start, 2 * QUERY_WINDOW + 1)]
        idx = abs_line - start
        if not (0 <= idx < len(lines)):
            return
        block = find_brace_block(lines, idx, col)
        if block is not None:
            text, (sl, sc), (el, ec) = block
            text = text.strip()
            if text:
                self.app.copy_query(text)
                self._select_block_visible(start + sl, sc, start + el, ec)
                return
        if pretty_json(lines[idx]) is not None:
            show_json_popup(self.app.root, lines[idx], self.app.theme, self.app.font_tuple)
        else:
            self.app.set_status_message("이 줄에서 쿼리({ }) 블록을 찾지 못했습니다")

    def _abs_file_line(self, render_line: int) -> int | None:
        """화면의 render_line(1-base)을 전체 파일 줄 번호로 변환."""
        base = self.model.top_line + (render_line - 1)
        if base < 0:
            return None
        if self._is_hide():
            fl = self.engine.get_filtered_lines(base, 1)
            return fl[0].line_no if fl else None
        return base

    def _select_block_visible(self, abs_sl: int, sc: int, abs_el: int, ec) -> None:
        """블록의 화면에 보이는 부분만 선택 표시(복사는 이미 끝남). hide 모드는 생략."""
        if self._is_hide():
            return
        top = self.model.top_line
        hi = top + self.model.viewport_lines - 1
        if abs_el < top or abs_sl > hi:
            return
        sr, scol = (abs_sl - top + 1, sc) if abs_sl >= top else (1, 0)
        er, ecol = (abs_el - top + 1, ec) if abs_el <= hi else (self.model.viewport_lines, "end")
        self.view.select_render(sr, scol, er, ecol)

    # ---- 외부 제어 -----------------------------------------------------

    def set_live(self, on: bool) -> None:
        self.live = on
        self.engine.set_follow(on)
        if on:
            self.auto = True
            self.model.goto_end()  # 수동 체크 → 맨 아래로(tail 효과)
        else:
            self.auto = False
        self.app.reflect_follow(self)  # 체크박스를 live&auto 상태로 동기화
        self.render()

    def apply_filter(self, pattern: str, mode: str, regex: bool, ignore_case: bool) -> None:
        self.filter_pattern = pattern
        self.filter_mode = mode
        self.filter_regex = regex
        self.filter_ignore_case = ignore_case
        self.engine.set_filter(pattern, mode=mode, regex=regex, ignore_case=ignore_case)
        self._match_cursor = None  # 검색어가 바뀌면 찾기 커서 초기화
        # 필터를 바꿔도 보던 위치를 유지한다 — 따라가는 중이면 맨 아래, 아니면 현재
        # top을 클램프만. (예전엔 무조건 맨 위로 튀어 highlight·모드 전환이 거슬렸다.)
        self.model.set_total(self._source_total())
        if self.live and self.auto:
            self.model.goto_end()
        else:
            self.model.set_top(self.model.top_line)
        self.render()

    def goto_next_match(self, forward: bool = True) -> None:
        """highlight 모드에서 다음(Enter)/이전(Shift+Enter) 일치 줄로 이동한다.

        끝까지 없으면 반대쪽 끝에서 다시 찾아 순환한다. 이동한 줄은 화면 가운데에
        두고 현재 일치 구간을 강조한다. hide 모드/검색어 없음이면 무동작.
        """
        if self.filter_mode == "hide" or not self.filter_pattern:
            return
        total = self.engine.get_total_lines()
        if total <= 0:
            return
        self.engine.start_match_scan()  # 개수/순위용 인덱스를 lazy로 시작(첫 탐색 시)
        if self._match_cursor is None:
            probe = self.model.top_line  # 첫 Enter는 현재 위치 포함해서 탐색
        else:
            probe = self._match_cursor + (1 if forward else -1)
        hit = self.engine.next_match_line(probe, forward=forward)
        wrapped = hit is None
        if hit is None:  # 끝 → 반대쪽 끝에서 순환
            hit = self.engine.next_match_line(0 if forward else total - 1, forward=forward)
        if hit is None:
            self.app.set_status_message("일치 항목 없음")
            return
        self._match_cursor = hit
        self._goto_centered(hit)  # 렌더 시 현재 일치 줄이 curmatch로 강조됨
        if wrapped:
            self.app.set_status_message("처음으로 돌아감" if forward else "끝으로 돌아감")

    def _goto_centered(self, line: int) -> None:
        self.model.set_top(self._centered_top(line, self.model.viewport_lines))
        self.auto = self.model.at_bottom()
        self.app.reflect_follow(self)
        self.render()

    def _centered_top(self, line: int, vp: int) -> int:
        """line을 화면 가운데 두는 top. 줄바꿈 OFF면 논리 줄 절반 위. ON이면 위쪽
        줄들의 표시행 수를 추정해 누적이 화면 절반에 닿는 지점을 top으로 잡는다
        (논리 줄 수로 계산하면 wrap된 줄이 화면을 넘겨 대상이 하단에 가려진다)."""
        half = vp // 2
        if not self.view._wrap or half <= 0 or line <= 0:
            return line - half
        above = self.engine.get_lines(max(0, line - vp), line - max(0, line - vp))
        acc = 0
        top = line
        for ln in reversed(above):  # line-1, line-2, ... 위로 누적
            acc += self.view.estimate_display_rows(ln.text)
            top = ln.line_no
            if acc >= half:
                break
        return top

    def match_count_text(self) -> str:
        """필터 일치 개수 표시. highlight 모드에서 탐색을 시작한 뒤에만 보인다.
        탐색 위치가 있으면 '현재/전체', 없으면 '전체건'. 스캔 중이면 ~ 표기."""
        if self.filter_mode == "hide" or not self.filter_pattern:
            return ""
        if not self.engine.match_scan_started():
            return ""
        total = self.engine.get_filtered_total()
        approx = "" if self.engine.is_filter_complete() else "~"
        if self._match_cursor is None:
            return f"{approx}{total:,}건"
        return f"{self.engine.match_rank(self._match_cursor):,}/{approx}{total:,}"

    def apply_theme(self) -> None:
        self.view.apply_theme(self.app.theme, self.app.classifier.colors())
        self.render()

    def status_text(self) -> str:
        total = self._source_total()
        cur = self.model.top_line + 1 if total else 0
        approx = "" if (self._is_hide() or self.engine.is_index_complete()) else "~"
        size = self.engine.get_size()
        parts = [f"Line {cur:,} / {approx}{total:,}", _fmt_size(size), self.encoding_label]
        parts.append("FOLLOW" if (self.live and self.auto) else ("LIVE" if self.live else "PAUSED"))
        if self._is_hide():
            parts.append(f"filter: {total:,} matches")
        elif self.filter_pattern:
            parts.append("filter: highlight")
        if not self.engine.is_index_complete():
            parts.append("indexing…")
        if self._status_msg:
            parts.append(self._status_msg)
        return "   |   ".join(parts)

    def close(self) -> None:
        self.engine.close()


class TabManager:
    def __init__(self, app, parent):
        self.app = app
        self.notebook = ttk.Notebook(parent)
        self.tabs: dict[str, LogTab] = {}
        self.notebook.bind("<<NotebookTabChanged>>", lambda e: app.on_tab_changed())

    def add(self, path: str) -> LogTab:
        tab = LogTab(self.app, path)
        self.notebook.add(tab.view, text=os.path.basename(path))
        self.tabs[str(tab.view)] = tab
        self.notebook.select(tab.view)
        return tab

    def current(self) -> LogTab | None:
        try:
            sel = self.notebook.select()
        except tk.TclError:
            return None
        return self.tabs.get(sel)

    def close_current(self) -> None:
        cur = self.current()
        if cur is None:
            return
        sel = self.notebook.select()
        self.notebook.forget(sel)
        self.tabs.pop(sel, None)
        cur.close()

    def all(self) -> list[LogTab]:
        return list(self.tabs.values())


def _fmt_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"
