from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .markdown_store import _atomic_write


@dataclass
class Preferences:
    theme: str = "warm"
    font_family: str = "system"
    scale: int = 100
    markdown_level: str = "balanced"
    auto_clear_completed: bool = False
    auto_snap_capsules: bool = True
    animations: bool = True
    language: str = "zh-CN"
    script_capsules_enabled: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def load_preferences(path: Path) -> Preferences:
    if not path.exists():
        return Preferences()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return Preferences()
    return Preferences(
        theme=str(payload.get("theme") or "warm"),
        font_family=str(payload.get("font_family") or "system"),
        scale=max(80, min(120, int(payload.get("scale") or 100))),
        markdown_level=str(payload.get("markdown_level") or "balanced"),
        auto_clear_completed=bool(payload.get("auto_clear_completed", False)),
        auto_snap_capsules=bool(payload.get("auto_snap_capsules", True)),
        animations=bool(payload.get("animations", True)),
        language=str(payload.get("language") or "zh-CN"),
        script_capsules_enabled=bool(
            payload.get("script_capsules_enabled", False)
        ),
    )


def save_preferences(path: Path, preferences: Preferences) -> None:
    _atomic_write(
        path,
        json.dumps(preferences.to_dict(), ensure_ascii=False, indent=2) + "\n",
    )


def update_preferences(path: Path, payload: dict[str, object]) -> Preferences:
    preferences = load_preferences(path)
    for name in preferences.to_dict():
        if name in payload:
            setattr(preferences, name, payload[name])
    preferences.scale = max(80, min(120, int(preferences.scale)))
    if preferences.theme not in {"system", "warm", "ink", "forest", "sunset"}:
        preferences.theme = "warm"
    if preferences.markdown_level not in {"plain", "balanced", "rich"}:
        preferences.markdown_level = "balanced"
    if preferences.language not in {"zh-CN", "en-US", "ja-JP", "ko-KR"}:
        preferences.language = "zh-CN"
    save_preferences(path, preferences)
    return preferences

