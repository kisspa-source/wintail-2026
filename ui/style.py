"""테마 dict → ttk 전체 위젯 스타일.

clam 베이스 위에 모든 ttk 위젯(Frame/Label/Button/Checkbutton/Entry/Combobox/
Notebook 탭/Scrollbar/Spinbox)을 한 벌의 테마색으로 칠한다. 평평한(flat) 모던 룩에
은은한 accent hover. 테마 변경 시 1회 호출 — 표준 라이브러리만 사용.
"""

from __future__ import annotations

from tkinter import ttk

WHITE = "#ffffff"


def _shift(color: str, delta: int) -> str:
    """hex 색을 delta만큼 밝게(+)/어둡게(-). 0~255로 클램프 — 베벨 음영 생성용."""
    c = color.lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    cl = lambda v: max(0, min(255, v + delta))  # noqa: E731
    return f"#{cl(r):02x}{cl(g):02x}{cl(b):02x}"


def _bevel(style: ttk.Style, name: str, face: str, fg: str, *, pad, arrow=None) -> None:
    """클래식 윈도우 버튼: 평소 raised(볼록), 누르면 sunken(들어감).
    위/왼쪽 밝은 모서리 + 아래/오른쪽 어두운 모서리로 입체감, 눌림 시 반전."""
    light, dark = _shift(face, 42), _shift(face, -46)
    cfg = dict(background=face, foreground=fg, relief="raised", borderwidth=2,
               padding=pad, lightcolor=light, darkcolor=dark, bordercolor=_shift(face, -78))
    if arrow:
        cfg["arrowcolor"] = arrow
    style.configure(name, **cfg)
    style.map(name,
              relief=[("pressed", "sunken"), ("!pressed", "raised")],
              background=[("pressed", _shift(face, -14)), ("active", _shift(face, 16))],
              lightcolor=[("pressed", dark)],   # 눌림: 베벨 반전 → 들어간 느낌
              darkcolor=[("pressed", light)])


def apply_style(style: ttk.Style, t: dict) -> None:
    try:
        style.theme_use("clam")
    except Exception:  # noqa: BLE001 — clam은 항상 있지만 방어
        pass

    bg, fg = t["toolbar_bg"], t["fg"]
    ctrl, ctrl_fg = t["control_bg"], t["control_fg"]
    accent, border = t["accent"], t["border"]

    # 공통 기본값
    style.configure(".", background=bg, foreground=fg, fieldbackground=ctrl,
                    bordercolor=border, lightcolor=border, darkcolor=border,
                    troughcolor=t["bg"], focuscolor=accent, relief="flat",
                    insertcolor=t["cursor"])

    style.configure("TFrame", background=bg)
    style.configure("TLabel", background=bg, foreground=fg)
    style.configure("Status.TLabel", background=t["status_bg"],
                    foreground=t["status_fg"], padding=(10, 4))

    # 영역 밴드(상단 메뉴 / 툴바)와 그 사이 구분선 — 영역을 또렷이 나눈다.
    style.configure("Menubar.TFrame", background=t["menubar_bg"])
    style.configure("Toolbar.TFrame", background=t["toolbar_bg"])
    style.configure("TSeparator", background=border)
    # 클릭 가능한 버튼류 — 클래식 윈도우처럼 볼록(raised), 누르면 들어감(sunken).
    _bevel(style, "Menubar.TMenubutton", t["menubar_bg"], fg, pad=(12, 5), arrow=fg)
    _bevel(style, "TButton", ctrl, ctrl_fg, pad=(12, 5))
    _bevel(style, "TMenubutton", ctrl, ctrl_fg, pad=(10, 5), arrow=ctrl_fg)

    style.configure("TCheckbutton", background=bg, foreground=fg, padding=(4, 2))
    style.map("TCheckbutton",
              background=[("active", bg)],
              foreground=[("active", fg)],
              indicatorcolor=[("selected", accent), ("!selected", ctrl)])

    style.configure("TEntry", fieldbackground=ctrl, foreground=ctrl_fg,
                    bordercolor=border, insertcolor=t["cursor"], padding=4)
    style.map("TEntry", bordercolor=[("focus", accent)])

    style.configure("TCombobox", fieldbackground=ctrl, foreground=ctrl_fg,
                    background=ctrl, arrowcolor=fg, bordercolor=border, padding=3)
    style.map("TCombobox",
              fieldbackground=[("readonly", ctrl)],
              foreground=[("readonly", ctrl_fg)],
              bordercolor=[("focus", accent)])

    style.configure("TSpinbox", fieldbackground=ctrl, foreground=ctrl_fg,
                    background=ctrl, arrowcolor=fg, bordercolor=border, padding=3)

    style.configure("TNotebook", background=bg, bordercolor=border, tabmargins=(2, 4, 2, 0))
    style.configure("TNotebook.Tab", background=ctrl, foreground=fg,
                    bordercolor=border, padding=(14, 6))
    style.map("TNotebook.Tab",
              background=[("selected", t["bg"])],
              foreground=[("selected", fg)],
              expand=[("selected", (1, 1, 1, 0))])

    # 느린 쿼리 패널 등 목록 표시용
    style.configure("Treeview", background=ctrl, fieldbackground=ctrl,
                    foreground=ctrl_fg, bordercolor=border)
    style.configure("Treeview.Heading", background=bg, foreground=fg, relief="flat",
                    padding=(6, 4))
    style.map("Treeview",
              background=[("selected", accent)],
              foreground=[("selected", WHITE)])
    style.map("Treeview.Heading", background=[("active", _shift(bg, 16))])

    for orient in ("Vertical", "Horizontal"):
        style.configure(f"{orient}.TScrollbar", background=ctrl, troughcolor=t["bg"],
                        bordercolor=border, arrowcolor=fg, relief="flat")
        style.map(f"{orient}.TScrollbar", background=[("active", accent)])


def apply_combobox_popup(root, t: dict) -> None:
    """콤보박스 드롭다운 리스트(별도 Listbox)는 ttk 스타일이 아니라 옵션 DB로 칠한다.
    이후 열리는 드롭다운에 적용된다."""
    root.option_add("*TCombobox*Listbox.background", t["control_bg"])
    root.option_add("*TCombobox*Listbox.foreground", t["control_fg"])
    root.option_add("*TCombobox*Listbox.selectBackground", t["accent"])
    root.option_add("*TCombobox*Listbox.selectForeground", WHITE)
