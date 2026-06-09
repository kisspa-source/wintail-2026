"""토스트 알림 테스트 — Tk 필요, 디스플레이 없으면 스킵."""

import time
import tkinter as tk

import pytest

from ui.theme import get_theme
from ui.toast import show_toast


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


def test_show_toast_creates_window(root):
    top = show_toast(root, "복사됨", get_theme("dark"), duration_ms=1)
    assert isinstance(top, tk.Toplevel)
    assert top.winfo_exists()


def test_toast_auto_dismisses(root):
    top = show_toast(root, "복사됨 (3자)", get_theme("dark"), duration_ms=1)
    for _ in range(200):
        root.update()
        if not top.winfo_exists():
            break
        time.sleep(0.003)
    assert not top.winfo_exists()
