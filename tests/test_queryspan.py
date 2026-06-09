"""enclosing_braces / find_brace_block 순수 로직 테스트 — Tk 비의존."""

from ui.queryspan import enclosing_braces, find_brace_block


def _sel(text, col):
    span = enclosing_braces(text, col)
    return None if span is None else text[span[0]:span[1]]


def test_basic_query():
    t = "Query:{SELECT * FROM t}[END]"
    assert _sel(t, 12) == "SELECT * FROM t"


def test_excludes_braces_and_trailer():
    t = "Query:{SELECT * FROM t}[END]"
    span = enclosing_braces(t, 12)
    assert t[span[0] - 1] == "{"   # 시작 직전이 여는 괄호
    assert t[span[1]] == "}"       # 끝이 닫는 괄호


def test_nested_innermost():
    assert _sel("a{b{c}d}e", 4) == "c"


def test_nested_outer():
    assert _sel("a{b{c}d}e", 2) == "b{c}d"


def test_click_on_opening_brace():
    assert _sel("x{q}y", 1) == "q"


def test_click_on_closing_brace():
    assert _sel("x{q}y", 3) == "q"


def test_no_braces_returns_none():
    assert enclosing_braces("plain query text", 3) is None


def test_outside_braces_returns_none():
    assert enclosing_braces("aa {q} bb", 0) is None


def test_unbalanced_open_returns_none():
    assert enclosing_braces("a{bc", 2) is None


def test_unbalanced_close_returns_none():
    assert enclosing_braces("ab}c", 1) is None


def test_empty_braces_returns_none():
    assert enclosing_braces("a{}b", 2) is None


def test_picks_pair_under_click():
    assert _sel("{a} {bb}", 6) == "bb"


def test_out_of_range_col_returns_none():
    assert enclosing_braces("no braces here", 9999) is None


# ---- find_brace_block (멀티라인) ------------------------------------------


def test_block_single_line():
    lines = ["Query:{SELECT * FROM t}[END]"]
    text, start, end = find_brace_block(lines, 0, 12)
    assert text == "SELECT * FROM t"
    assert start == (0, 7)
    assert end == (0, 22)


def test_block_multiline_click_middle():
    lines = ["Query:{", "SELECT *", "FROM t", "}[END]"]
    text, start, end = find_brace_block(lines, 1, 2)  # 'SELECT' 줄 클릭
    assert text == "\nSELECT *\nFROM t\n"
    assert start == (0, 7)   # 여는 { 바로 다음
    assert end == (3, 0)     # 닫는 } 위치


def test_block_multiline_click_other_line_same_block():
    lines = ["Query:{", "SELECT *", "FROM t", "}[END]"]
    a = find_brace_block(lines, 1, 0)
    b = find_brace_block(lines, 2, 3)  # 'FROM t' 줄 클릭 → 같은 블록
    assert a[0] == b[0] == "\nSELECT *\nFROM t\n"


def test_block_no_braces_returns_none():
    assert find_brace_block(["plain line", "another"], 0, 3) is None


def test_block_click_outside_returns_none():
    lines = ["prefix only", "{ inside }", "suffix"]
    assert find_brace_block(lines, 0, 2) is None   # 블록 밖 줄 클릭


def test_block_nested_innermost_across_lines():
    lines = ["a{", "b{c}d", "}e"]
    text, _, _ = find_brace_block(lines, 1, 3)  # 'c' 위치 → 안쪽 {c}
    assert text == "c"


def test_block_empty_lines_returns_none():
    assert find_brace_block([], 0, 0) is None
