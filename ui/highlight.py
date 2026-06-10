"""로그 레벨 분류 + 색상 규칙 + 사용자 다중 하이라이트 규칙.

가시 영역의 각 줄에만 적용되므로 비용이 거의 없다. 기본 규칙(ERROR/FATAL 빨강,
WARN 주황, INFO 파랑, DEBUG 회색)을 제공하며 config.py를 통해 사용자가 패턴·색을
편집할 수 있다. 색은 다크/라이트 모두에서 읽히는 테마 독립 hex로 둔다.

HighlightRules는 사용자가 정의한 여러 패턴을 각각 다른 배경색으로 칠하는 규칙
(보기 ▸ 하이라이트 규칙…)이다. 규칙당 Matcher 하나, 칠하기는 보이는 줄에만.
"""

from __future__ import annotations

import re

from engine.filterscanner import Matcher

# name, pattern(대소문자 무시, 단어 경계), color(hex)
DEFAULT_LEVEL_RULES: list[dict[str, str]] = [
    {"name": "error", "pattern": r"\b(?:ERROR|FATAL|CRITICAL|SEVERE|EXCEPTION)\b", "color": "#e05252"},
    {"name": "warn", "pattern": r"\b(?:WARN|WARNING)\b", "color": "#d9a441"},
    {"name": "info", "pattern": r"\b(?:INFO|NOTICE)\b", "color": "#4f9fd1"},
    {"name": "debug", "pattern": r"\b(?:DEBUG|TRACE)\b", "color": "#9a9a9a"},
]


class LevelClassifier:
    def __init__(self, rules: list[dict[str, str]] | None = None):
        self.rules = rules if rules is not None else DEFAULT_LEVEL_RULES
        self._compiled: list[tuple[str, re.Pattern, str]] = []
        for r in self.rules:
            try:
                pat = re.compile(r["pattern"], re.IGNORECASE)
            except re.error:
                continue
            self._compiled.append((r["name"], pat, r.get("color", "#cccccc")))

    def classify(self, text: str) -> dict[str, str] | None:
        """첫 번째로 매칭되는 규칙(name, color)을 반환. 없으면 None."""
        for name, pat, color in self._compiled:
            if pat.search(text):
                return {"name": name, "color": color}
        return None

    def colors(self) -> dict[str, str]:
        return {name: color for name, _, color in self._compiled}


class HighlightRules:
    """사용자 정의 다중 하이라이트 — 패턴별 배경색.

    rules: [{"pattern": str, "color": "#hex", "regex": bool, "ignore_case": bool}, ...]
    spans()는 가시 영역의 줄에만 호출되어 메모리/성능 영향이 없다.
    잘못된 정규식은 Matcher.valid로 걸러져 조용히 무시된다(앱은 계속 동작).
    """

    def __init__(self, rules: list[dict] | None):
        self.rules = [dict(r) for r in (rules or []) if isinstance(r, dict)]
        self._matchers: list[Matcher] = [
            Matcher(str(r.get("pattern", "")), regex=bool(r.get("regex", False)),
                    ignore_case=bool(r.get("ignore_case", True)))
            for r in self.rules
        ]

    def colors(self) -> list[str]:
        """규칙 순서대로의 배경색 목록(태그 hlr<i>와 1:1)."""
        return [str(r.get("color", "#fff2a8")) for r in self.rules]

    def spans(self, text: str) -> list[tuple[int, int, int]]:
        """텍스트 내 모든 규칙의 매칭 구간 [(규칙 번호, start, end), ...]."""
        out: list[tuple[int, int, int]] = []
        for i, m in enumerate(self._matchers):
            if not m.valid or not m.pattern:
                continue
            for s, e in m.find_spans(text):
                out.append((i, s, e))
        return out
