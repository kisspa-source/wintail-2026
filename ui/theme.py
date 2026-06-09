"""테마 프리셋 — 창 크롬·본문·위젯 전체 색.

각 프리셋은 동일한 키 집합을 갖는다. 본문/거터/매칭 색뿐 아니라 위젯 크롬
(toolbar_bg, control_bg/control_fg, accent, border)까지 포함해 ttk 스타일과
tk 위젯 전부를 한 벌의 색으로 칠한다. 외부 의존성 없이 dict만 쓴다.

키:
  bg/fg                 본문·창 기본 배경/글자
  gutter_bg/gutter_fg   줄번호 거터
  select_bg             선택 영역
  match_bg              필터 하이라이트
  current_match_bg      현재 일치 줄 강조(진함)
  cursor                캐럿
  menubar_bg            상단 메뉴바 밴드(가장 짙음/구분용)
  toolbar_bg            툴바/탭바 등 크롬 배경
  control_bg/control_fg 버튼·입력창·콤보 등 컨트롤
  accent                활성/선택/포커스 강조색
  border                영역 구분선/얇은 경계
  status_bg/status_fg   하단 상태바

영역 구분: menubar_bg ≠ toolbar_bg ≠ bg 로 상단 메뉴/툴바/본문이 또렷한 밴드를
이루고, 그 사이를 border 색 구분선으로 나눈다.
"""

from __future__ import annotations

THEMES: dict[str, dict[str, str]] = {
    "Light+": {
        "bg": "#ffffff", "fg": "#1f1f1f",
        "gutter_bg": "#f7f7f7", "gutter_fg": "#9aa0a6",
        "select_bg": "#add6ff", "match_bg": "#fff2a8", "current_match_bg": "#ffd24d",
        "cursor": "#1f1f1f",
        "menubar_bg": "#e4e4e4", "toolbar_bg": "#f3f3f3",
        "control_bg": "#ffffff", "control_fg": "#1f1f1f",
        "accent": "#0066b8", "border": "#d0d0d0",
        "status_bg": "#0a6fb8", "status_fg": "#ffffff",
    },
    "Dark+": {
        "bg": "#1e1e1e", "fg": "#d4d4d4",
        "gutter_bg": "#1e1e1e", "gutter_fg": "#6e7681",
        "select_bg": "#264f78", "match_bg": "#5a4a00", "current_match_bg": "#b3860b",
        "cursor": "#d4d4d4",
        "menubar_bg": "#252526", "toolbar_bg": "#333337",
        "control_bg": "#3c3c3c", "control_fg": "#e0e0e0",
        "accent": "#0e639c", "border": "#454548",
        "status_bg": "#007acc", "status_fg": "#ffffff",
    },
    "Monokai": {
        "bg": "#272822", "fg": "#f8f8f2",
        "gutter_bg": "#272822", "gutter_fg": "#75715e",
        "select_bg": "#49483e", "match_bg": "#565449", "current_match_bg": "#a6911f",
        "cursor": "#f8f8f0",
        "menubar_bg": "#141510", "toolbar_bg": "#1e1f1c",
        "control_bg": "#3e3d32", "control_fg": "#f8f8f2",
        "accent": "#75715e", "border": "#3e3d32",
        "status_bg": "#a6911f", "status_fg": "#272822",
    },
    "One Dark": {
        "bg": "#282c34", "fg": "#abb2bf",
        "gutter_bg": "#282c34", "gutter_fg": "#636d83",
        "select_bg": "#3e4451", "match_bg": "#4a4528", "current_match_bg": "#9e7d00",
        "cursor": "#528bff",
        "menubar_bg": "#1b1f24", "toolbar_bg": "#21252b",
        "control_bg": "#3a3f4b", "control_fg": "#abb2bf",
        "accent": "#3e6ea5", "border": "#3a3f4b",
        "status_bg": "#4078f2", "status_fg": "#ffffff",
    },
    "Dracula": {
        "bg": "#282a36", "fg": "#f8f8f2",
        "gutter_bg": "#282a36", "gutter_fg": "#6272a4",
        "select_bg": "#44475a", "match_bg": "#544c2e", "current_match_bg": "#a68a00",
        "cursor": "#f8f8f2",
        "menubar_bg": "#16171e", "toolbar_bg": "#21222c",
        "control_bg": "#44475a", "control_fg": "#f8f8f2",
        "accent": "#6272a4", "border": "#44475a",
        "status_bg": "#bd93f9", "status_fg": "#282a36",
    },
    "Solarized Dark": {
        "bg": "#002b36", "fg": "#93a1a1",
        "gutter_bg": "#002b36", "gutter_fg": "#586e75",
        "select_bg": "#073642", "match_bg": "#4a3a0a", "current_match_bg": "#b58900",
        "cursor": "#93a1a1",
        "menubar_bg": "#04262f", "toolbar_bg": "#073642",
        "control_bg": "#0a4554", "control_fg": "#93a1a1",
        "accent": "#268bd2", "border": "#0a4554",
        "status_bg": "#268bd2", "status_fg": "#fdf6e3",
    },
}

DEFAULT_THEME = "Light+"

# 예전 config가 쓰던 이름 → 새 프리셋
_ALIASES = {"dark": "Dark+", "light": "Light+"}


def theme_names() -> list[str]:
    return list(THEMES.keys())


def resolve_name(name: str | None) -> str:
    if name in THEMES:
        return name
    if name in _ALIASES:
        return _ALIASES[name]
    return DEFAULT_THEME


def get_theme(name: str | None) -> dict[str, str]:
    return THEMES[resolve_name(name)]
