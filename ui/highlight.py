"""로그 레벨 분류 + 색상 규칙.

가시 영역의 각 줄에만 적용되므로 비용이 거의 없다. 기본 규칙(ERROR/FATAL 빨강,
WARN 주황, INFO 파랑, DEBUG 회색)을 제공하며 config.py를 통해 사용자가 패턴·색을
편집할 수 있다. 색은 다크/라이트 모두에서 읽히는 테마 독립 hex로 둔다.
"""

from __future__ import annotations

import re

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
