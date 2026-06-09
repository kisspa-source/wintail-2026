"""ViewportModel 단위 테스트 (Tk 비의존 순수 로직).

가상 스크롤의 핵심 수학: top_line 클램핑, 스크롤바 분율 매핑, 페이지/라인 이동,
바닥 판정(follow 재개에 사용).
"""

from ui.viewport import ViewportModel


def test_clamp_top_to_max():
    m = ViewportModel()
    m.set_viewport_lines(10)
    m.set_total(100)
    m.set_top(95)
    assert m.top_line == 90  # max_top = 100 - 10
    m.set_top(-5)
    assert m.top_line == 0


def test_small_file_max_top_zero():
    m = ViewportModel()
    m.set_viewport_lines(50)
    m.set_total(10)
    assert m.max_top() == 0
    m.set_top(5)
    assert m.top_line == 0


def test_scroll_fractions():
    m = ViewportModel()
    m.set_viewport_lines(10)
    m.set_total(100)
    m.set_top(20)
    first, last = m.scroll_fractions()
    assert abs(first - 0.20) < 1e-9
    assert abs(last - 0.30) < 1e-9


def test_scroll_fractions_empty_file():
    m = ViewportModel()
    m.set_viewport_lines(10)
    m.set_total(0)
    assert m.scroll_fractions() == (0.0, 1.0)


def test_moveto_fraction():
    m = ViewportModel()
    m.set_viewport_lines(10)
    m.set_total(1000)
    m.moveto(0.5)
    assert m.top_line == 500


def test_page_and_line_scroll():
    m = ViewportModel()
    m.set_viewport_lines(10)
    m.set_total(100)
    m.set_top(0)
    m.page(1)
    assert m.top_line == 10
    m.scroll_lines(3)
    assert m.top_line == 13
    m.page(-1)
    assert m.top_line == 3


def test_at_bottom_and_goto_end():
    m = ViewportModel()
    m.set_viewport_lines(10)
    m.set_total(100)
    assert m.at_bottom() is False
    m.goto_end()
    assert m.top_line == 90
    assert m.at_bottom() is True


def test_total_shrink_reclamps_top():
    m = ViewportModel()
    m.set_viewport_lines(10)
    m.set_total(100)
    m.set_top(80)
    m.set_total(20)  # 트렁케이션 등으로 총 줄 수 감소
    assert m.top_line <= m.max_top()
    assert m.top_line == 10
