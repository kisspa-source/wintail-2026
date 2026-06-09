"""설정 영속화 (%APPDATA%/wintail-2026/config.json).

테마, 폰트, 레벨 규칙(패턴·색), 최근 파일, follow 기본값 등을 저장한다.
파일이 없거나 손상되면 기본값으로 동작한다.
"""

from __future__ import annotations

import json
import os

from ui.highlight import DEFAULT_LEVEL_RULES

DEFAULTS: dict = {
    "theme": "Light+",
    "font_family": "",  # 빈 값이면 시작 시 자동 선택
    "font_size": 11,
    "wrap": False,  # 자동 줄바꿈 (전역)
    "follow_default": True,
    "encoding_default": "",  # 빈 값이면 자동 감지
    "level_rules": DEFAULT_LEVEL_RULES,
    "recent_files": [],
    "max_recent": 10,
}


def config_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "wintail-2026")


def config_path() -> str:
    return os.path.join(config_dir(), "config.json")


def load(path: str | None = None) -> dict:
    path = path or config_path()
    data: dict = {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    merged = dict(DEFAULTS)
    if isinstance(data, dict):
        merged.update(data)
    return merged


def save(cfg: dict, path: str | None = None) -> None:
    path = path or config_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except OSError:
        pass  # 설정 저장 실패는 치명적이지 않다


def push_recent(cfg: dict, file_path: str) -> None:
    recent = [p for p in cfg.get("recent_files", []) if p != file_path]
    recent.insert(0, file_path)
    cfg["recent_files"] = recent[: cfg.get("max_recent", 10)]
