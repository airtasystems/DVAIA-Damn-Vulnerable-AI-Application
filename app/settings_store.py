"""UI-managed settings persisted under data/ (writable in Docker volume mounts)."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_FILE = ROOT / "data" / "dvaia_settings.json"
ENV_FILE = ROOT / ".env"


def _read_json() -> Dict[str, Any]:
    if not SETTINGS_FILE.is_file():
        return {}
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(data: Dict[str, Any]) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def get_ui_reset_data_on_start_override() -> Optional[bool]:
    """Return UI override when set; None when unset (fall back to env)."""
    val = _read_json().get("reset_data_on_start")
    if val is None:
        return None
    return bool(val)


def set_reset_data_on_start(enabled: bool) -> Dict[str, Any]:
    """Persist reset-on-start preference to data/dvaia_settings.json and .env when writable."""
    data = _read_json()
    data["reset_data_on_start"] = enabled
    _write_json(data)
    env_updated = upsert_env_var("RESET_DATA_ON_START", "true" if enabled else "false")
    return {
        "reset_data_on_start": enabled,
        "settings_file": str(SETTINGS_FILE.relative_to(ROOT)),
        "env_updated": env_updated,
    }


def upsert_env_var(key: str, value: str) -> bool:
    """Update or append key=value in .env; also patch os.environ for this process."""
    if not ENV_FILE.is_file():
        return False
    try:
        text = ENV_FILE.read_text(encoding="utf-8")
        pattern = rf"^{re.escape(key)}=.*$"
        line = f"{key}={value}"
        if re.search(pattern, text, flags=re.MULTILINE):
            text = re.sub(pattern, line, text, count=1, flags=re.MULTILINE)
        else:
            text = text.rstrip() + "\n" + line + "\n"
        ENV_FILE.write_text(text, encoding="utf-8")
        os.environ[key] = value
        return True
    except OSError:
        return False
