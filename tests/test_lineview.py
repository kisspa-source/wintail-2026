"""LineView 줄바꿈/폰트 메트릭 테스트 — Tk 필요, 디스플레이 없으면 스킵."""

import tkinter as tk
import tkinter.font as tkfont

import pytest

from ui.lineview import LineView, estimate_wrapped_rows
from ui.theme import get_theme


def test_estimate_wrapped_rows():
    assert estimate_wrapped_rows("", 40) == 1
    assert estimate_wrapped_rows("a" * 40, 40) == 1
    assert estimate_wrapped_rows("a" * 41, 40) == 2
    assert estimate_wrapped_rows("a" * 100, 40) == 3
    assert estimate_wrapped_rows("가" * 20, 40) == 1    # 와이드 문자=2칸 → 40칸
    assert estimate_wrapped_rows("가" * 21, 40) == 2
    assert estimate_wrapped_rows("x", 0) == 1           # cols 0 방어


@pytest.fixture(scope="module")
def root():
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("디스플레이 없음 — GUI 테스트 스킵")
    r.withdraw()
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass


def _make_view(root):
    font = tkfont.Font(family="TkFixedFont", size=11)
    return LineView(root, font, get_theme("dark")), font


def test_set_wrap_toggles_content_option(root):
    view, _ = _make_view(root)
    view.set_wrap(True)
    assert str(view.content.cget("wrap")) == "word"
    view.set_wrap(False)
    assert str(view.content.cget("wrap")) == "none"


class _LN:
    def __init__(self, line_no, text):
        self.line_no = line_no
        self.text = text


class _Cls:
    def classify(self, text):
        return None


def test_wrap_hides_gutter_off_restores(root):
    view, _ = _make_view(root)
    assert view.gutter.grid_info()        # 기본(off): 거터 표시
    view.set_wrap(True)
    assert not view.gutter.grid_info()    # wrap ON: 거터 숨김
    view.set_wrap(False)
    assert view.gutter.grid_info()        # 복귀


def test_wrap_render_does_not_query_displaylines(root):
    """느림의 근본 원인: wrap 렌더가 표시행 레이아웃을 동기 조회하던 것.
    수정 후 wrap 렌더는 content.count를 절대 호출하지 않아야 한다."""
    view, _ = _make_view(root)
    view.set_wrap(True)

    def boom(*a, **k):
        raise AssertionError("wrap 렌더가 표시행을 조회하면 안 됨")

    view.content.count = boom
    lines = [_LN(0, "x" * 600), _LN(1, "short"), _LN(2, "y" * 600)]
    view.render(lines, _Cls(), lambda t: [])  # 예외 없이 통과해야 함


def test_recompute_line_px_tracks_font_size(root):
    view, font = _make_view(root)
    before = view._line_px
    font.configure(size=24)
    view.recompute_line_px()
    assert view._line_px > before


class _Evt:
    def __init__(self, delta, state):
        self.delta = delta
        self.state = state


def test_ctrl_wheel_zooms_not_scrolls(root):
    view, _ = _make_view(root)
    zoom, scroll = [], []
    view.cb_zoom = zoom.append
    view.cb_line = scroll.append
    view._on_wheel(_Evt(delta=120, state=0x4))   # Ctrl + 휠 위 → 확대
    view._on_wheel(_Evt(delta=-120, state=0x4))  # Ctrl + 휠 아래 → 축소
    assert zoom == [1, -1]
    assert scroll == []


def test_plain_wheel_scrolls_not_zooms(root):
    view, _ = _make_view(root)
    zoom, scroll = [], []
    view.cb_zoom = zoom.append
    view.cb_line = scroll.append
    view._on_wheel(_Evt(delta=-120, state=0))
    assert scroll and not zoom


def test_on_double_forwards_render_coords(root):
    view, _ = _make_view(root)
    got = []
    view.cb_dblclick = lambda line, col: got.append((line, col))
    view.content.index = lambda spec: "3.7"  # @x,y → 줄.칸
    view._on_double(type("E", (), {"x": 0, "y": 0})())
    assert got == [(3, 7)]


def test_select_render_sets_sel_across_lines(root):
    view, _ = _make_view(root)
    view.render([_LN(0, "0123456789"), _LN(1, "abcdefghij")], _Cls(), lambda t: [])
    view.select_render(1, 2, 2, 5)
    rng = view.content.tag_ranges("sel")
    assert rng and view.content.get(rng[0], rng[1]) == "23456789\nabcde"


def test_mark_current_highlights_one_line(root):
    view, _ = _make_view(root)
    view.render([_LN(0, "aaa"), _LN(1, "bbb"), _LN(2, "ccc")], _Cls(), lambda t: [])
    view.mark_current(2)
    rng = view.content.tag_ranges("curmatch")
    assert rng and view.content.get(rng[0], rng[1]) == "bbb"
    view.mark_current(None)  # 해제
    assert not view.content.tag_ranges("curmatch")


def test_select_render_clamps_to_content(root):
    view, _ = _make_view(root)
    view.render([_LN(0, "short")], _Cls(), lambda t: [])
    view.select_render(1, 0, 9, "end")  # 끝 줄 번호가 내용 범위를 넘어도 안전
    rng = view.content.tag_ranges("sel")
    assert rng and view.content.get(rng[0], rng[1]) == "short"
