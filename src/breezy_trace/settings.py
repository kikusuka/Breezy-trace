"""Tiny local preferences file (currently just the theme). Never leaves this machine."""

import json
from contextlib import suppress
from pathlib import Path

from breezy_trace.config import data_dir


def settings_path() -> Path:
    return data_dir() / "settings.json"


def load_settings() -> dict[str, str]:
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        key: value for key, value in data.items() if isinstance(key, str) and isinstance(value, str)
    }


def save_setting(key: str, value: str) -> None:
    settings = load_settings()
    settings[key] = value
    # Preferences are a convenience; never fail the app over them.
    with suppress(OSError):
        settings_path().write_text(json.dumps(settings, indent=2), encoding="utf-8")
