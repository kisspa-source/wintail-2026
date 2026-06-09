"""ViewportModel — 가상 스크롤의 순수 상태/수학 (Tk 비의존).

위젯에는 항상 화면에 보이는 만큼(viewport_lines)만 채우고, 이 모델이 top_line과
총 줄 수를 추적하며 스크롤바 분율을 계산한다. 모든 입력(휠/페이지/드래그)은
set_top/moveto/page/scroll_lines로 수렴한다.
"""

from __future__ import annotations


class ViewportModel:
    def __init__(self) -> None:
        self.top_line = 0
        self.viewport_lines = 1
        self.total_lines = 0

    def set_viewport_lines(self, n: int) -> None:
        self.viewport_lines = max(1, n)
        self._clamp()

    def set_total(self, n: int) -> None:
        self.total_lines = max(0, n)
        self._clamp()

    def max_top(self) -> int:
        return max(0, self.total_lines - self.viewport_lines)

    def set_top(self, line: int) -> None:
        self.top_line = line
        self._clamp()

    def scroll_lines(self, delta: int) -> None:
        self.set_top(self.top_line + delta)

    def page(self, n: int) -> None:
        self.set_top(self.top_line + n * self.viewport_lines)

    def goto_end(self) -> None:
        self.set_top(self.max_top())

    def at_bottom(self) -> bool:
        return self.top_line >= self.max_top()

    def moveto(self, fraction: float) -> None:
        self.set_top(round(fraction * self.total_lines))

    def scroll_fractions(self) -> tuple[float, float]:
        if self.total_lines <= 0:
            return (0.0, 1.0)
        first = self.top_line / self.total_lines
        last = (self.top_line + self.viewport_lines) / self.total_lines
        return (_clamp01(first), _clamp01(last))

    def _clamp(self) -> None:
        top = self.top_line
        if top < 0:
            top = 0
        m = self.max_top()
        if top > m:
            top = m
        self.top_line = top


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x
