"""헤드리스 스모크 테스트 — App을 mainloop 없이 구동해 배선/렌더 오류를 잡는다.

디스플레이가 없으면 (TclError) 스킵한다.
"""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

import pytest

wintail = pytest.importorskip("wintail")


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("디스플레이 없음 — GUI 스모크 테스트 스킵")
    r.withdraw()
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass


def _pump_until_indexed(root, tab, app, ticks=200):
    import time

    for _ in range(ticks):
        root.update()
        app._pump_tick()
        if tab.engine.is_index_complete():
            return
        time.sleep(0.003)


def test_open_render_filter_scroll(root, tmp_path):
    app = wintail.App(root)
    app.pump.stop()  # 테스트는 수동으로 펌프한다

    data = b"".join(
        (b"ERROR line %d\n" % i) if i % 4 == 0 else (b"INFO line %d\n" % i)
        for i in range(500)
    )
    p = tmp_path / "smoke.log"
    p.write_bytes(data)

    app.open_file(str(p))
    tab = app.tabs.current()
    assert tab is not None

    _pump_until_indexed(root, tab, app)
    assert tab.engine.is_index_complete()
    assert tab.engine.get_total_lines() == 500

    # 렌더가 예외 없이 동작
    tab.model.set_viewport_lines(20)
    tab.render()
    root.update()

    # 스크롤 동작
    tab._on_goto("end")
    tab._on_line(-5)
    tab._on_page(-1)
    tab._on_moveto(0.5)
    root.update()

    # hide 필터
    tab.apply_filter("ERROR", "hide", False, False)
    _wait_filter_complete(app, root, tab)  # 백그라운드 스캔 완료까지 (sleep 포함, 견고)
    assert tab.engine.get_filtered_total() == 125  # 500/4
    tab.render()
    root.update()

    # highlight 필터
    tab.apply_filter("line", "highlight", False, False)
    tab.render()
    root.update()

    # 테마 전환
    app.toggle_theme()
    root.update()

    # 정리
    for t in app.tabs.all():
        t.close()


def test_open_missing_file_does_not_crash(root, tmp_path, monkeypatch):
    # 모달 메시지박스는 테스트에서 블로킹되므로 무력화
    monkeypatch.setattr(wintail.messagebox, "showerror", lambda *a, **k: None)
    app = wintail.App(root)
    app.pump.stop()
    # 존재하지 않는 경로 — 앱이 죽지 않고 탭도 생성되지 않아야 한다
    app.open_file(str(tmp_path / "does_not_exist.log"))
    assert len(app.tabs.all()) == 0
    root.update()
    # 이후 정상 파일은 잘 열려야 한다
    p = tmp_path / "ok.log"
    p.write_bytes(b"a\nb\n")
    app.open_file(str(p))
    assert len(app.tabs.all()) == 1
    for t in app.tabs.all():
        t.close()


def test_font_size_change_clamps_and_persists(root, monkeypatch):
    saved = {}
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: saved.update(c))
    app = wintail.App(root)
    app.pump.stop()
    app._set_font_size(1000)
    assert app._font_size == wintail.FONT_SIZE_MAX
    assert app.font_tuple == (app._font_family, wintail.FONT_SIZE_MAX)
    app._set_font_size(0)
    assert app._font_size == wintail.FONT_SIZE_MIN
    assert saved.get("font_size") == wintail.FONT_SIZE_MIN
    for t in app.tabs.all():
        t.close()


def test_wrap_toggle_applies_to_open_tabs(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    p = tmp_path / "w.log"
    p.write_bytes(b"".join(b"line %d\n" % i for i in range(20)))
    app.open_file(str(p))
    tab = app.tabs.current()
    app.wrap_var.set(True)
    app._on_wrap_toggle()
    assert str(tab.view.content.cget("wrap")) == "word"
    assert app.config["wrap"] is True
    app.wrap_var.set(False)
    app._on_wrap_toggle()
    assert str(tab.view.content.cget("wrap")) == "none"
    for t in app.tabs.all():
        t.close()


def test_new_tab_inherits_wrap(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    app._wrap = True
    app.wrap_var.set(True)
    p = tmp_path / "w2.log"
    p.write_bytes(b"a\nb\n")
    app.open_file(str(p))
    tab = app.tabs.current()
    assert str(tab.view.content.cget("wrap")) == "word"
    for t in app.tabs.all():
        t.close()


def test_set_font_family_updates_font_and_config(root, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    target = next((f for f in tkfont.families(root) if f and f != app._font_family),
                  app._font_family)
    app._set_font_family(target)
    assert app._font_family == target
    assert app.config["font_family"] == target
    assert app.font_tuple[0] == target
    for t in app.tabs.all():
        t.close()


def test_copy_query_sets_clipboard_and_status(root, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    app.copy_query("SELECT * FROM t")
    assert root.clipboard_get() == "SELECT * FROM t"
    assert "복사" in app.status.cget("text")
    app.copy_query("")  # 빈 문자열은 무시 — 클립보드 유지
    assert root.clipboard_get() == "SELECT * FROM t"


def test_singleline_query_double_click_copies(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    q = "Query:{SELECT * FROM users WHERE id=42}[END]"
    p = tmp_path / "q.log"
    p.write_bytes((q + "\n").encode("utf-8"))
    app.open_file(str(p))
    tab = app.tabs.current()
    _pump_until_indexed(root, tab, app)
    tab.model.set_viewport_lines(20)
    tab.model.set_top(0)
    tab.render()
    root.update()
    tab._on_dblclick(1, q.index("SELECT"))  # render line 1, 쿼리 내부
    assert root.clipboard_get() == "SELECT * FROM users WHERE id=42"
    for t in app.tabs.all():
        t.close()


def test_multiline_query_double_click_copies(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    lines = ["before", "Query:{", "  SELECT *", "  FROM users", "  WHERE id=42", "}[END]", "after"]
    p = tmp_path / "mq.log"
    p.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    app.open_file(str(p))
    tab = app.tabs.current()
    _pump_until_indexed(root, tab, app)
    tab.model.set_viewport_lines(20)
    tab.model.set_top(0)
    tab.render()
    root.update()
    tab._on_dblclick(3, 4)  # 'SELECT' 줄(파일 3번째) 중간 클릭 → 블록 전체
    assert root.clipboard_get() == "SELECT *\n  FROM users\n  WHERE id=42"
    for t in app.tabs.all():
        t.close()


def test_tab_wires_dblclick_callback(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    p = tmp_path / "q.log"
    p.write_bytes(b"Query:{SELECT 1}[END]\n")
    app.open_file(str(p))
    tab = app.tabs.current()
    assert tab.view.cb_dblclick == tab._on_dblclick
    for t in app.tabs.all():
        t.close()


def test_copy_query_shows_toast(root, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    app.copy_query("SELECT 1")
    assert app._toast is not None and app._toast.winfo_exists()
    first = app._toast
    app.copy_query("SELECT 2")          # 연속 복사 → 이전 토스트 제거
    assert not first.winfo_exists()
    assert app._toast is not first and app._toast.winfo_exists()


def test_double_click_no_block_sets_status(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    p = tmp_path / "plain.log"
    p.write_bytes(b"just a plain log line without braces\n")
    app.open_file(str(p))
    tab = app.tabs.current()
    _pump_until_indexed(root, tab, app)
    tab.model.set_viewport_lines(20)
    tab.model.set_top(0)
    tab.render()
    root.update()
    tab._on_dblclick(1, 5)  # 블록 없음 → 조용히 끝나지 않고 상태바 안내
    assert "찾지" in app.status.cget("text")
    for t in app.tabs.all():
        t.close()


def _open_indexed(app, root, tmp_path, name, n=500):
    p = tmp_path / name
    p.write_bytes(b"".join(b"line %d\n" % i for i in range(n)))
    app.open_file(str(p))
    tab = app.tabs.current()
    _pump_until_indexed(root, tab, app)
    tab.model.set_viewport_lines(20)
    return tab


def test_highlight_filter_keeps_scroll_position(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_indexed(app, root, tmp_path, "hl.log")
    tab.live = False
    tab.auto = False          # 스크롤 올린 상태(따라가는 중 아님)
    tab.model.set_top(100)
    tab.apply_filter("line", "highlight", False, False)
    assert tab.model.top_line == 100   # 맨 위(0)로 튀지 않고 위치 유지
    for t in app.tabs.all():
        t.close()


def test_scroll_up_unchecks_follow_keeps_engine(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_indexed(app, root, tmp_path, "fo.log")
    tab.set_live(True)                 # 따라가기 on → 바닥
    assert app.follow_var.get() is True
    tab._on_line(-100)                 # 위로 스크롤
    assert tab.auto is False
    assert tab.live is True            # 엔진은 계속 읽음(데이터 안 놓침)
    assert app.follow_var.get() is False   # 체크 해제
    tab._on_goto("end")                # 다시 바닥으로
    assert tab.auto is True
    assert app.follow_var.get() is True    # 다시 체크
    for t in app.tabs.all():
        t.close()


def test_manual_follow_check_tails_to_bottom(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_indexed(app, root, tmp_path, "ta.log")
    tab.set_live(False)                # 따라가기 끔
    tab.model.set_top(0)               # 맨 위로
    assert app.follow_var.get() is False
    tab.set_live(True)                 # 수동 체크
    assert tab.live is True and tab.auto is True
    assert tab.model.at_bottom()       # 바닥으로 tail
    assert app.follow_var.get() is True
    for t in app.tabs.all():
        t.close()


def _open_with_matches(app, root, tmp_path, name="m.log"):
    # ERROR가 0,10,20,30,40 줄에
    data = b"".join((b"ERROR %d\n" % i) if i % 10 == 0 else (b"ok %d\n" % i) for i in range(50))
    p = tmp_path / name
    p.write_bytes(data)
    app.open_file(str(p))
    tab = app.tabs.current()
    _pump_until_indexed(root, tab, app)
    tab.view.set_wrap(False)   # 실제 config의 wrap값에 흔들리지 않도록 고정
    tab.model.set_viewport_lines(10)
    tab.set_live(False)
    tab.model.set_top(0)
    tab.apply_filter("ERROR", "highlight", False, False)
    return tab


def test_goto_next_match_cycles(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_with_matches(app, root, tmp_path)
    assert tab._match_cursor is None
    cursors = []
    for _ in range(6):
        tab.goto_next_match(forward=True)
        cursors.append(tab._match_cursor)
    assert cursors == [0, 10, 20, 30, 40, 0]  # 마지막 이후 처음으로 순환
    for t in app.tabs.all():
        t.close()


def test_centered_top_wrap_uses_estimate(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_with_matches(app, root, tmp_path)
    # 비줄바꿈: 논리 줄 기준 가운데
    tab.view.set_wrap(False)
    assert tab._centered_top(20, 10) == 15      # 20 - 10//2
    # 줄바꿈: 표시행 추정 누적 기준(각 줄 3행 가정 → 위로 2줄이면 6행>=5)
    tab.view.set_wrap(True)
    tab.view.estimate_display_rows = lambda text: 3
    assert tab._centered_top(20, 10) == 18
    for t in app.tabs.all():
        t.close()


def test_goto_next_match_centers(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_with_matches(app, root, tmp_path)
    tab.goto_next_match(forward=True)  # 0
    tab.goto_next_match(forward=True)  # 10
    tab.goto_next_match(forward=True)  # 20
    assert tab._match_cursor == 20
    assert tab.model.top_line == 15    # 가운데: 20 - 10//2
    for t in app.tabs.all():
        t.close()


def test_goto_prev_match_wraps(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_with_matches(app, root, tmp_path)
    tab.goto_next_match(forward=True)   # 첫 일치 0으로
    assert tab._match_cursor == 0
    tab.goto_next_match(forward=False)  # 0보다 위 없음 → 끝(40)으로 순환
    assert tab._match_cursor == 40
    for t in app.tabs.all():
        t.close()


def test_apply_filter_resets_match_cursor(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_with_matches(app, root, tmp_path)
    tab.goto_next_match(forward=True)
    assert tab._match_cursor == 0
    tab.apply_filter("ok", "highlight", False, False)  # 검색어 변경
    assert tab._match_cursor is None
    for t in app.tabs.all():
        t.close()


def test_filter_enter_navigates_matches(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_with_matches(app, root, tmp_path)
    app.filter_var.set("ERROR")        # 툴바 값 = 탭 상태(변경 없음 → 재적용 안 함)
    app._on_filter_enter(forward=True)
    assert tab._match_cursor == 0
    app._on_filter_enter(forward=True)
    assert tab._match_cursor == 10
    app._on_filter_enter(forward=False)
    assert tab._match_cursor == 0
    for t in app.tabs.all():
        t.close()


def test_filter_enter_applies_when_changed(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_with_matches(app, root, tmp_path)  # 현재 필터 "ERROR"
    app.filter_var.set("ok")           # 새 검색어 → Enter 시 먼저 적용 후 이동
    app._on_filter_enter(forward=True)
    assert tab.filter_pattern == "ok"
    assert tab._match_cursor is not None   # "ok" 첫 일치로 이동함
    for t in app.tabs.all():
        t.close()


def _wait_filter_complete(app, root, tab):
    import time
    for _ in range(400):
        app._pump_tick()
        root.update()
        if tab.engine.is_filter_complete():
            return
        time.sleep(0.005)


def test_match_count_text(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_with_matches(app, root, tmp_path)
    assert tab.match_count_text() == ""        # 탐색 전엔 비움(스캔 안 함)
    tab.goto_next_match(forward=True)          # → 0, 스캔 시작
    _wait_filter_complete(app, root, tab)
    tab.goto_next_match(forward=True)          # → 10 (2번째)
    assert tab.match_count_text() == "2/5"
    for t in app.tabs.all():
        t.close()


def test_navigation_marks_current_line(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_with_matches(app, root, tmp_path)
    assert not tab.view.content.tag_ranges("curmatch")
    tab.goto_next_match(forward=True)          # → 0, 화면 내 → 강조
    assert tab.view.content.tag_ranges("curmatch")


def test_app_match_label_reflects_navigation(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_with_matches(app, root, tmp_path)
    tab.goto_next_match(forward=True)
    _wait_filter_complete(app, root, tab)
    tab.render()                               # update_status가 라벨 갱신
    assert app.match_var.get() == "1/5"
    for t in app.tabs.all():
        t.close()


def test_debounced_reapply_keeps_match_cursor(root, tmp_path, monkeypatch):
    # 버그: 천천히 Enter를 누르면 그 사이 디바운스 _apply_filter_now가 발화해
    # apply_filter가 _match_cursor를 리셋 → 다음 Enter가 처음부터 다시 찾음.
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_with_matches(app, root, tmp_path)
    app.filter_var.set("ERROR")
    app._on_filter_enter(forward=True)  # 0
    app._on_filter_enter(forward=True)  # 10
    assert tab._match_cursor == 10
    app._apply_filter_now()             # 디바운스 발화(텍스트 변화 없음)
    assert tab._match_cursor == 10      # 커서 유지되어야(리셋 금지)
    app._on_filter_enter(forward=True)  # → 20 (버그면 다시 0/10)
    assert tab._match_cursor == 20
    for t in app.tabs.all():
        t.close()


def test_theme_combo_applies_and_persists(root, monkeypatch):
    saved = {}
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: saved.update(dict(c)))
    app = wintail.App(root)
    app.pump.stop()
    app._apply_theme_named("Dark+")        # 알려진 시작점
    app.theme_var.set("Monokai")           # 콤보 선택 → trace → 적용
    assert app.theme_name == "Monokai"
    assert app.theme == wintail.get_theme("Monokai")
    assert saved.get("theme") == "Monokai"
    for t in app.tabs.all():
        t.close()


def test_theme_applies_to_content_not_chrome(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    p = tmp_path / "c.log"
    p.write_bytes(b"hello world\n")
    app.open_file(str(p))
    tab = app.tabs.current()
    app._apply_theme_named("Monokai")
    mono, light = wintail.get_theme("Monokai"), wintail.get_theme("Light+")
    # 컨텐츠는 선택 테마(Monokai)
    assert str(tab.view.content.cget("bg")) == mono["bg"]
    # 크롬은 Light+ 고정
    assert app.style.lookup("TFrame", "background") == light["toolbar_bg"]
    assert app.style.lookup("Status.TLabel", "background") == light["status_bg"]
    for t in app.tabs.all():
        t.close()


def test_toggle_theme_cycles(root, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    names = wintail.theme_names()
    app._apply_theme_named(names[0])
    app.toggle_theme()
    assert app.theme_name == names[1]
    app.toggle_theme()
    assert app.theme_name == names[2]
    for t in app.tabs.all():
        t.close()


def test_custom_themed_menubar(root, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    assert str(root.cget("menu")) == ""          # 네이티브 메뉴바 미사용
    assert isinstance(app._menubar_frame, ttk.Frame)
    app._apply_theme_named("Monokai")
    # 메뉴(크롬)는 선택 테마와 무관하게 크롬 테마(Light+)로 고정
    assert str(app._menus[0].cget("bg")) == wintail.get_theme(wintail.CHROME_THEME)["control_bg"]
    for t in app.tabs.all():
        t.close()


def test_legacy_theme_name_resolved(root, monkeypatch):
    # 예전 config "dark"/"light"가 새 프리셋으로 매핑되어 로드된다
    monkeypatch.setattr(wintail.cfg, "load", lambda p=None: {**wintail.cfg.DEFAULTS, "theme": "dark"})
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    assert app.theme_name == "Dark+"
    for t in app.tabs.all():
        t.close()


# ---- 화면 지우기(표시만 비움 — 파일/인덱스 불변) ---------------------------


def _pump_until(root, app, cond, ticks=400):
    import time

    for _ in range(ticks):
        app._pump_tick()
        root.update()
        if cond():
            return
        time.sleep(0.005)


def test_clear_display_empties_view_but_keeps_file(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_indexed(app, root, tmp_path, "clr.log")  # 500줄
    tab.set_live(False)
    app.clear_display()
    assert tab._source_total() == 0
    assert tab.view.content.get("1.0", "end-1c") == ""   # 화면은 비워짐
    assert tab.engine.get_total_lines() == 500           # 인덱스는 그대로
    assert (tmp_path / "clr.log").stat().st_size > 0     # 실제 파일 불변
    assert "지움" in tab.status_text()
    for t in app.tabs.all():
        t.close()


def test_clear_display_shows_only_new_lines(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    p = tmp_path / "tailclr.log"
    p.write_bytes(b"".join(b"old %d\n" % i for i in range(100)))
    app.open_file(str(p))
    tab = app.tabs.current()
    _pump_until_indexed(root, tab, app)
    tab.view.set_wrap(False)
    tab.model.set_viewport_lines(10)
    tab.set_live(True)
    tab.clear_display()
    assert tab._source_total() == 0
    with open(p, "ab") as f:
        f.write(b"new A\nnew B\n")
    _pump_until(root, app, lambda: tab.engine.get_total_lines() >= 102)
    tab.render()
    assert tab._source_total() == 2
    text = tab.view.content.get("1.0", "end-1c")
    assert "new A" in text and "old" not in text
    for t in app.tabs.all():
        t.close()


def test_restore_display_brings_back_old_lines(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_indexed(app, root, tmp_path, "rst.log")
    tab.view.set_wrap(False)
    tab.set_live(False)
    tab.clear_display()
    assert tab._source_total() == 0
    tab.restore_display()
    assert tab._source_total() == 500
    # 복원 직후엔 지웠던 지점(끝부분)이 보인다 — 보던 위치 유지
    assert "line 49" in tab.view.content.get("1.0", "end-1c")
    tab._on_goto("home")
    assert "line 0" in tab.view.content.get("1.0", "end-1c")
    for t in app.tabs.all():
        t.close()


def test_clear_display_maps_abs_line_and_source_total(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_indexed(app, root, tmp_path, "map.log")
    tab.set_live(False)
    tab._clear_line = 100               # 기준 줄을 중간에 둔 경우(절대 줄)
    tab.model.set_top(0)
    assert tab._source_total() == 400
    assert tab._abs_file_line(1) == 100  # 화면 첫 줄 = 파일 100번 줄
    for t in app.tabs.all():
        t.close()


def test_clear_display_with_hide_filter_rows(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_with_matches(app, root, tmp_path)        # ERROR가 0,10,20,30,40줄
    tab.apply_filter("ERROR", "hide", False, False)
    _wait_filter_complete(app, root, tab)
    assert tab._source_total() == 5
    tab._clear_line = 25                # 25줄 앞의 일치 3개(0,10,20)가 숨는다
    assert tab._source_total() == 2
    assert [ln.line_no for ln in tab._fetch(0, 10)] == [30, 40]
    tab.restore_display()
    assert tab._source_total() == 5
    for t in app.tabs.all():
        t.close()


def test_goto_next_match_skips_cleared(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_with_matches(app, root, tmp_path)        # highlight, 일치 0,10,20,30,40
    tab._clear_line = 25
    cursors = []
    for _ in range(3):
        tab.goto_next_match(forward=True)
        cursors.append(tab._match_cursor)
    assert cursors == [30, 40, 30]      # 숨겨진 0/10/20은 건너뛰고 순환도 기준 뒤에서
    tab.goto_next_match(forward=False)  # 30에서 뒤로 → 앞쪽은 숨김 → 끝(40)으로 순환
    assert tab._match_cursor == 40
    for t in app.tabs.all():
        t.close()


def test_match_count_text_excludes_cleared(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_with_matches(app, root, tmp_path)
    tab._clear_line = 25
    tab.goto_next_match(forward=True)   # → 30, 스캔 시작
    _wait_filter_complete(app, root, tab)
    assert tab.match_count_text() == "1/2"
    for t in app.tabs.all():
        t.close()


def test_truncate_resets_clear(root, tmp_path, monkeypatch):
    from engine.events import Truncated

    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_indexed(app, root, tmp_path, "trunc.log")
    tab.clear_display()
    assert tab._clear_line == 500
    tab.handle_events([Truncated(0)], active=True)       # 로테이션 → 지우기 해제
    assert tab._clear_line == 0
    for t in app.tabs.all():
        t.close()


def test_app_clear_display_without_tab_is_noop(root, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    app.clear_display()                 # 탭 없음 — 무동작/무예외
    app.restore_display()


# ---- 느린 쿼리 패널 --------------------------------------------------------


def _open_slow_log(app, root, tmp_path, name="slow.log"):
    lines = [f"line {i}" for i in range(200)]
    lines[50] = "x Time:1500 [QET:NORMAL] slow one"
    lines[120] = "y Time:30000 [QET:SLOW] slower"
    lines[130] = "z Time:200 [QET:NORMAL] fast"
    p = tmp_path / name
    p.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    app.open_file(str(p))
    tab = app.tabs.current()
    _pump_until_indexed(root, tab, app)
    tab.view.set_wrap(False)
    tab.model.set_viewport_lines(10)
    tab.set_live(False)
    tab.model.set_top(0)
    return tab


def test_slow_panel_scan_lists_hits_and_navigates(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_slow_log(app, root, tmp_path)

    app.toggle_slow_panel()
    panel = app._slow_panel
    assert panel is not None and panel.winfo_exists()
    assert panel.tree.bind("<<TreeviewSelect>>")     # 클릭 배선 존재

    panel.threshold_var.set("1.0")                   # 1초 이상
    panel.scan()
    _pump_until(root, app, lambda: tab.engine.is_slow_scan_complete() and panel._shown >= 2)
    assert panel._shown == 2
    # Tk는 숫자 형태 값("51")을 int로 돌려주므로 str로 맞춰 비교
    assert [str(v) for v in panel.tree.item("0")["values"]] == ["51", "1,500 ms"]  # 1-base 줄
    assert [str(v) for v in panel.tree.item("1")["values"]] == ["121", "30,000 ms"]
    assert panel.info_var.get().startswith("완료: 2건")

    panel.tree.selection_set("1")                    # 두 번째(파일 120줄) 클릭
    panel._on_select()
    # 패널이 열리며 실제 리사이즈로 viewport_lines가 갱신되므로 현재 값 기준으로 검증
    assert tab.model.top_line == 120 - tab.model.viewport_lines // 2  # 가운데 배치
    # 포커스가 패널에 있어도 보이는 전용 강조(gotoline) — sel 태그가 아님
    assert tab.view.content.tag_ranges("gotoline")
    for t in app.tabs.all():
        t.close()


def test_slow_panel_invalid_threshold_message(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    app.toggle_slow_panel()
    panel = app._slow_panel
    panel.threshold_var.set("abc")
    panel.scan()
    assert "올바르지" in panel.info_var.get()
    panel.threshold_var.set("1.0")
    panel.scan()                                     # 열린 탭 없음 안내
    assert "열린 로그" in panel.info_var.get()
    for t in app.tabs.all():
        t.close()


def test_slow_panel_toggle_closes_and_stops(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_slow_log(app, root, tmp_path, "tg.log")
    app.toggle_slow_panel()
    panel = app._slow_panel
    panel.threshold_var.set("0.1")
    panel.scan()
    app.toggle_slow_panel()                          # 닫기 → 스캔 중단 + 위젯 제거
    assert app._slow_panel is None
    assert not panel.winfo_exists()
    assert tab.engine.slow_hit_count() == 0          # stop_slow_scan으로 정리됨
    for t in app.tabs.all():
        t.close()


def test_slow_panel_resets_when_tab_closed(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_slow_log(app, root, tmp_path, "cl.log")
    app.toggle_slow_panel()
    panel = app._slow_panel
    panel.threshold_var.set("1.0")
    panel.scan()
    _pump_until(root, app, lambda: tab.engine.is_slow_scan_complete() and panel._shown >= 2)
    app.close_tab()                                  # 스캔했던 탭 닫힘
    assert panel._tab is None
    assert panel._shown == 0
    assert "닫혔" in panel.info_var.get()
    for t in app.tabs.all():
        t.close()


def test_goto_line_mark_follows_scroll_and_rerender(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_slow_log(app, root, tmp_path, "mk.log")
    tab.goto_line(120)
    assert tab._goto_mark == 120
    assert tab.view.content.tag_ranges("gotoline")
    tab.render()                                     # 라이브 갱신 시뮬레이션 → 강조 유지
    assert tab.view.content.tag_ranges("gotoline")
    tab.model.set_top(0)                             # 멀리 스크롤 → 화면 밖이면 해제
    tab.render()
    assert not tab.view.content.tag_ranges("gotoline")
    tab.goto_line(120)                               # 다시 이동 → 다시 표시
    assert tab.view.content.tag_ranges("gotoline")
    tab.clear_display()                              # 화면 지우기 → 강조도 해제
    assert tab._goto_mark is None
    assert not tab.view.content.tag_ranges("gotoline")
    for t in app.tabs.all():
        t.close()


def test_goto_line_blocked_by_hide_or_clear(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_slow_log(app, root, tmp_path, "gd.log")
    # 화면 지우기로 숨긴 영역 → 이동하지 않고 안내
    tab._clear_line = 150
    tab.goto_line(120)
    assert "복원" in app.status.cget("text")
    assert tab.model.top_line == 0
    tab._clear_line = 0
    # hide 필터 중 → 이동하지 않고 안내
    tab.apply_filter("Time", "hide", False, False)
    _wait_filter_complete(app, root, tab)
    tab.goto_line(120)
    assert "hide" in app.status.cget("text")
    for t in app.tabs.all():
        t.close()


# ---- 검색 결과 패널 ----------------------------------------------------------


def test_search_panel_lists_matches_and_navigates(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_with_matches(app, root, tmp_path)        # ERROR가 0,10,20,30,40줄(highlight)
    app.toggle_search_panel()
    panel = app._search_panel
    assert panel is not None
    panel.scan()
    _pump_until(root, app, lambda: tab.engine.is_filter_complete() and panel._shown >= 5)
    assert panel._shown == 5
    assert [str(v) for v in panel.tree.item("2")["values"]] == ["21", "ERROR 20"]
    assert panel.info_var.get().startswith("완료 5건")
    panel.tree.selection_set("2")                        # 줄 20으로 이동
    panel._on_select()
    assert tab.model.top_line == max(0, 20 - tab.model.viewport_lines // 2)
    assert tab.view.content.tag_ranges("gotoline")
    for t in app.tabs.all():
        t.close()


def test_search_panel_requires_pattern_and_resets_on_filter_change(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_indexed(app, root, tmp_path, "sp.log")
    app.toggle_search_panel()
    panel = app._search_panel
    panel.scan()                                         # 필터 비어 있음 → 안내
    assert "검색어" in panel.info_var.get()
    tab.apply_filter("line", "highlight", False, False)
    panel.scan()
    _pump_until(root, app, lambda: tab.engine.is_filter_complete() and panel._shown > 0)
    assert panel._shown > 0
    tab.apply_filter("0", "highlight", False, False)     # 필터 변경 → 결과 무효
    assert panel._tab is None and panel._shown == 0
    assert "다시 검색" in panel.info_var.get()
    for t in app.tabs.all():
        t.close()


def test_search_panel_paging_with_more_button(root, tmp_path, monkeypatch):
    from ui import searchpanel

    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    monkeypatch.setattr(searchpanel, "PAGE", 3)          # 페이지 크기를 줄여 검증
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_with_matches(app, root, tmp_path)        # 일치 5건 > PAGE 3
    app.toggle_search_panel()
    panel = app._search_panel
    panel.scan()
    _pump_until(root, app, lambda: tab.engine.is_filter_complete() and panel._shown >= 3)
    assert panel._shown == 3
    assert "표시 3" in panel.info_var.get()
    assert panel.more_btn.winfo_manager() == "pack"      # 더 보기 노출
    panel._more()
    assert panel._shown == 5
    assert panel.more_btn.winfo_manager() == ""          # 다 보였으면 숨김
    for t in app.tabs.all():
        t.close()


def test_right_side_panels_are_exclusive(root, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    app.toggle_slow_panel()
    assert app._slow_panel is not None
    app.toggle_search_panel()                            # 검색 패널 → 느린 쿼리 닫힘
    assert app._slow_panel is None and app._search_panel is not None
    app.toggle_slow_panel()                              # 반대 방향도 동일
    assert app._search_panel is None and app._slow_panel is not None
    app.toggle_slow_panel()
    assert app._slow_panel is None


# ---- 북마크 ---------------------------------------------------------------


def test_bookmark_toggle_via_gutter_marks_and_unmarks(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_indexed(app, root, tmp_path, "bm.log")
    tab.view.set_wrap(False)
    tab.set_live(False)
    tab.model.set_top(0)
    tab.render()
    tab.toggle_bookmark(5)                 # 거터 클릭과 동일 경로(render line 5 → 줄 4)
    tab.toggle_bookmark(10)
    assert tab._bookmarks == [4, 9]
    assert tab.view.gutter.tag_ranges("bm")          # 거터에 표시
    assert "북마크 추가" in app.status.cget("text")
    tab.toggle_bookmark(5)                 # 같은 줄 다시 → 제거
    assert tab._bookmarks == [9]
    assert "북마크 제거" in app.status.cget("text")
    for t in app.tabs.all():
        t.close()


def test_bookmark_navigation_cycles_and_marks(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_indexed(app, root, tmp_path, "bmn.log")
    tab.view.set_wrap(False)
    tab.set_live(False)
    tab.model.set_top(0)
    tab.render()
    tab.toggle_bookmark(5)                 # 줄 4
    tab.model.set_top(100)
    tab.render()
    tab.toggle_bookmark(1)                 # 줄 100
    tab.model.set_top(0)
    cursors = []
    for fwd in (True, True, True, False):
        tab.goto_next_bookmark(forward=fwd)
        cursors.append(tab._bm_cursor)
    assert cursors == [4, 100, 4, 100]     # 순환(앞으로 끝→처음, 뒤로 처음→끝)
    assert tab._goto_mark == 100           # 이동 줄 강조 재사용
    for t in app.tabs.all():
        t.close()


def test_bookmark_empty_and_hide_messages(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_indexed(app, root, tmp_path, "bme.log")
    tab.set_live(False)
    tab.goto_next_bookmark()
    assert "북마크가 없습니다" in app.status.cget("text")
    tab.apply_filter("line", "hide", False, False)
    _wait_filter_complete(app, root, tab)
    tab.goto_next_bookmark()
    assert "hide" in app.status.cget("text")
    for t in app.tabs.all():
        t.close()


def test_bookmarks_cleared_on_truncate(root, tmp_path, monkeypatch):
    from engine.events import Truncated

    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_indexed(app, root, tmp_path, "bmt.log")
    tab.set_live(False)
    tab.model.set_top(0)
    tab.render()
    tab.toggle_bookmark(3)
    assert tab._bookmarks
    tab.handle_events([Truncated(0)], active=True)
    assert tab._bookmarks == [] and tab._bm_cursor is None
    for t in app.tabs.all():
        t.close()


# ---- 다중 하이라이트 규칙 ----------------------------------------------------


def test_highlight_rules_paint_visible_lines(root, tmp_path, monkeypatch):
    saved = {}
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: saved.update(dict(c)))
    app = wintail.App(root)
    app.pump.stop()
    p = tmp_path / "hl.log"
    p.write_bytes(b"alpha one\nplain\nbeta two\n" * 5)
    app.open_file(str(p))
    tab = app.tabs.current()
    _pump_until_indexed(root, tab, app)
    tab.view.set_wrap(False)
    tab.set_live(False)
    tab.model.set_viewport_lines(15)
    tab.model.set_top(0)
    app._apply_highlight_rules([
        {"pattern": "alpha", "color": "#ff0000", "regex": False, "ignore_case": True},
        {"pattern": "beta", "color": "#00ff00", "regex": False, "ignore_case": True},
    ])
    assert tab.view.content.tag_ranges("hlr0") and tab.view.content.tag_ranges("hlr1")
    assert str(tab.view.content.tag_cget("hlr0", "background")) == "#ff0000"
    assert saved.get("highlight_rules")[0]["pattern"] == "alpha"   # 설정 저장
    app._apply_highlight_rules([])                                 # 규칙 제거 → 태그 제거
    assert not tab.view.content.tag_ranges("hlr0")
    for t in app.tabs.all():
        t.close()


def test_highlight_rules_invalid_regex_does_not_crash(root, tmp_path, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    app = wintail.App(root)
    app.pump.stop()
    tab = _open_indexed(app, root, tmp_path, "hbad.log")
    app._apply_highlight_rules([{"pattern": "([", "regex": True, "color": "#fff"}])
    tab.render()                                                   # 예외 없이 렌더
    assert not tab.view.content.tag_ranges("hlr0")
    for t in app.tabs.all():
        t.close()


def test_rule_dialog_add_update_delete(root, monkeypatch):
    monkeypatch.setattr(wintail.cfg, "save", lambda c, p=None: None)
    from ui.ruledialog import RuleDialog

    received = []
    dlg = RuleDialog(root, wintail.get_theme("Light+"), [], received.append)
    dlg.pattern_var.set("ERROR")
    dlg.add_rule()
    assert received[-1][0]["pattern"] == "ERROR"
    assert received[-1][0]["ignore_case"] is True                  # 기본: 대소문자 무시
    dlg.tree.selection_set("0")                                    # 선택 → 필드 로드
    root.update()    # <<TreeviewSelect>>는 큐 이벤트라 처리 루프를 한 번 돌려야 한다
    assert dlg.pattern_var.get() == "ERROR"
    dlg.pattern_var.set("WARN")
    dlg.case_var.set(True)                                         # 대소문자 구분
    dlg.update_selected()
    assert received[-1][0] == {"pattern": "WARN", "color": received[-1][0]["color"],
                               "regex": False, "ignore_case": False}
    dlg.tree.selection_set("0")
    dlg.delete_selected()
    assert received[-1] == []
    dlg.top.destroy()


def test_multi_tab(root, tmp_path):
    app = wintail.App(root)
    app.pump.stop()
    paths = []
    for n in range(3):
        p = tmp_path / f"f{n}.log"
        p.write_bytes(b"".join(b"x %d\n" % i for i in range(50)))
        paths.append(str(p))
        app.open_file(str(p))
    assert len(app.tabs.all()) == 3
    # 탭 전환
    app.tabs.notebook.select(app.tabs.all()[0].view)
    app.on_tab_changed()
    root.update()
    app.tabs.close_current()
    assert len(app.tabs.all()) == 2
    for t in app.tabs.all():
        t.close()
