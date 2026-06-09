"""클릭 지점을 감싸는 중괄호 { } 쌍의 안쪽 범위를 찾는다(Tk 비의존).

로그의 'Query:{ ... }[END]' 처럼 구분된 쿼리를 더블클릭으로 통째로 선택/복사할 때
쓰인다. 중첩을 고려해 클릭 위치를 가장 가깝게 감싸는 쌍을 고르고, 괄호는 제외한
안쪽 내용의 (start, end) 문자 오프셋을 돌려준다. 감싸는 쌍이 없거나 짝이 안 맞거나
안쪽이 비면 None.
"""

from __future__ import annotations


def enclosing_braces(text: str, col: int) -> tuple[int, int] | None:
    col = max(0, min(col, len(text)))

    # 스택으로 짝이 맞는 { } 쌍을 모은다(짝 없는 괄호는 버린다).
    stack: list[int] = []
    pairs: list[tuple[int, int]] = []
    for i, ch in enumerate(text):
        if ch == "{":
            stack.append(i)
        elif ch == "}" and stack:
            pairs.append((stack.pop(), i))

    # col을 감싸는(o <= col <= c) 쌍 중 가장 안쪽(여는 위치가 가장 큰) 것.
    best: tuple[int, int] | None = None
    for o, c in pairs:
        if o <= col <= c and (best is None or o > best[0]):
            best = (o, c)
    if best is None:
        return None
    o, c = best
    if o + 1 >= c:  # 빈 { }
        return None
    return (o + 1, c)


def find_brace_block(lines, click_line: int, click_col: int):
    """여러 줄에 걸친 { } 블록을 찾는다.

    lines를 개행으로 이어 enclosing_braces로 균형 매칭한 뒤, 안쪽 텍스트(개행 포함)와
    시작/끝 좌표를 돌려준다. 반환: (inner_text, (start_line, start_col),
    (end_line, end_col)) 또는 None. 좌표는 lines 기준이며 end는 배타적이다.
    """
    if not lines:
        return None
    click_line = max(0, min(click_line, len(lines) - 1))
    joined = "\n".join(lines)
    offset = sum(len(lines[i]) + 1 for i in range(click_line))
    offset += max(0, min(click_col, len(lines[click_line])))
    span = enclosing_braces(joined, offset)
    if span is None:
        return None
    s, e = span
    return joined[s:e], _offset_to_lc(lines, s), _offset_to_lc(lines, e)


def _offset_to_lc(lines, offset: int) -> tuple[int, int]:
    run = 0
    for i, ln in enumerate(lines):
        if offset <= run + len(ln):
            return (i, offset - run)
        run += len(ln) + 1  # 개행 1칸 포함
    last = len(lines) - 1
    return (last, len(lines[last]))
