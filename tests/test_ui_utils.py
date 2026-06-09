"""순수 UI 유틸 테스트: LevelClassifier, pretty_json, config, theme."""

from ui.config import DEFAULTS, load, push_recent, save
from ui.highlight import DEFAULT_LEVEL_RULES, LevelClassifier
from ui.jsonpanel import pretty_json
from ui.theme import DEFAULT_THEME, THEMES, get_theme, theme_names


# ---- LevelClassifier ------------------------------------------------------


def test_classify_levels():
    c = LevelClassifier(DEFAULT_LEVEL_RULES)
    assert c.classify("2020-01-01 ERROR boom")["name"] == "error"
    assert c.classify("FATAL crash")["name"] == "error"
    assert c.classify("WARN low disk")["name"] == "warn"
    assert c.classify("app INFO ready")["name"] == "info"
    assert c.classify("DEBUG x=1")["name"] == "debug"
    assert c.classify("just a plain line") is None


def test_classify_priority_error_over_warn():
    c = LevelClassifier(DEFAULT_LEVEL_RULES)
    # 같은 줄에 ERROR와 WARN이 있으면 error가 우선
    assert c.classify("ERROR after WARN")["name"] == "error"


def test_classify_case_insensitive():
    c = LevelClassifier(DEFAULT_LEVEL_RULES)
    assert c.classify("an error happened")["name"] == "error"


# ---- pretty_json ----------------------------------------------------------


def test_pretty_plain_object():
    out = pretty_json('{"a":1,"b":[2,3]}')
    assert out is not None
    assert '"a": 1' in out


def test_pretty_with_log_prefix():
    out = pretty_json('2020-01-01 INFO {"x": {"y": 1}}')
    assert out is not None
    assert '"y": 1' in out


def test_pretty_trailing_text_ignored():
    out = pretty_json('{"ok": true} <-- response')
    assert out is not None
    assert '"ok": true' in out


def test_pretty_invalid_returns_none():
    assert pretty_json("not json at all") is None
    assert pretty_json("") is None


def test_pretty_korean_preserved():
    out = pretty_json('{"msg":"에러 발생"}')
    assert out is not None
    assert "에러 발생" in out


# ---- config ---------------------------------------------------------------


def test_load_missing_returns_defaults(tmp_path):
    cfg = load(str(tmp_path / "nope.json"))
    assert cfg["theme"] == DEFAULTS["theme"]
    assert cfg["level_rules"] == DEFAULT_LEVEL_RULES


def test_save_load_roundtrip(tmp_path):
    p = str(tmp_path / "sub" / "config.json")
    cfg = load(p)
    cfg["theme"] = "light"
    cfg["font_size"] = 14
    save(cfg, p)
    again = load(p)
    assert again["theme"] == "light"
    assert again["font_size"] == 14


def test_defaults_include_wrap_off():
    assert DEFAULTS["wrap"] is False


def test_wrap_roundtrip(tmp_path):
    p = str(tmp_path / "config.json")
    cfg = load(p)
    cfg["wrap"] = True
    save(cfg, p)
    assert load(p)["wrap"] is True


def test_corrupt_config_falls_back(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{ not valid json", encoding="utf-8")
    cfg = load(str(p))
    assert cfg["theme"] == DEFAULTS["theme"]


def test_push_recent_dedups_and_caps():
    cfg = dict(DEFAULTS)
    cfg["recent_files"] = []
    cfg["max_recent"] = 3
    for f in ["a", "b", "c", "a", "d"]:
        push_recent(cfg, f)
    assert cfg["recent_files"] == ["d", "a", "c"]


# ---- theme ----------------------------------------------------------------


REQUIRED_THEME_KEYS = {
    "bg", "fg", "gutter_bg", "gutter_fg", "select_bg", "match_bg",
    "current_match_bg", "cursor", "menubar_bg", "toolbar_bg",
    "control_bg", "control_fg", "accent", "border", "status_bg", "status_fg",
}


def test_all_presets_have_required_keys():
    assert len(theme_names()) >= 6
    for name in theme_names():
        assert REQUIRED_THEME_KEYS <= set(THEMES[name].keys()), name


def test_get_theme_unknown_falls_back():
    assert get_theme("nonexistent") == THEMES[DEFAULT_THEME]


def test_get_theme_legacy_aliases():
    # 예전 config의 "dark"/"light" 이름을 새 프리셋으로 매핑
    assert get_theme("dark") == THEMES["Dark+"]
    assert get_theme("light") == THEMES["Light+"]


def test_default_is_light_plus_and_first():
    assert DEFAULT_THEME == "Light+"
    assert DEFAULTS["theme"] == "Light+"
    assert theme_names()[0] == "Light+"   # 콤보 맨 위


def test_regions_have_distinct_bands():
    # 메뉴바·툴바·본문 배경이 서로 달라 영역이 구분되어야 한다
    for name in theme_names():
        t = THEMES[name]
        assert len({t["menubar_bg"], t["toolbar_bg"], t["bg"]}) == 3, name
