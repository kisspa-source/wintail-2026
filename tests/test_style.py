"""ttk 스타일 적용기 테스트 — Tk 필요, 디스플레이 없으면 스킵."""

import tkinter as tk
from tkinter import ttk

import pytest

from ui.style import _shift, apply_style
from ui.theme import get_theme


def test_shift_lightens_darkens_and_clamps():
    assert _shift("#000000", 16) == "#101010"
    assert _shift("#ffffff", 16) == "#ffffff"   # 상한 클램프
    assert _shift("#808080", -16) == "#707070"
    assert _shift("#000000", -16) == "#000000"  # 하한 클램프


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


def test_apply_style_sets_widget_colors(root):
    style = ttk.Style(root)
    t = get_theme("Dark+")
    apply_style(style, t)
    assert style.theme_use() == "clam"
    assert style.lookup("TButton", "background") == t["control_bg"]
    assert style.lookup("TFrame", "background") == t["toolbar_bg"]
    assert style.lookup("TLabel", "foreground") == t["fg"]
    assert style.lookup("Status.TLabel", "background") == t["status_bg"]


def test_buttons_are_raised(root):
    style = ttk.Style(root)
    apply_style(style, get_theme("Light+"))
    assert str(style.lookup("TButton", "relief")) == "raised"
    assert str(style.lookup("TMenubutton", "relief")) == "raised"
    assert int(style.lookup("TButton", "borderwidth")) >= 1
    # 베벨: 위/왼쪽 밝은 모서리 ≠ 아래/오른쪽 어두운 모서리
    assert style.lookup("TButton", "lightcolor") != style.lookup("TButton", "darkcolor")


def test_apply_style_switches_theme(root):
    style = ttk.Style(root)
    mono = get_theme("Monokai")
    apply_style(style, mono)
    assert style.lookup("TFrame", "background") == mono["toolbar_bg"]
    assert style.lookup("TButton", "background") == mono["control_bg"]
