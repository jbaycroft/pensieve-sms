"""preferences.py — per-user, per-action preference store.
Stored at VAULT_ROOT/.pensieve-app/preferences.json
"""
import json
import logging
import pathlib
from .vault import vault_root

log = logging.getLogger(__name__)
_APP_DIR: pathlib.Path | None = None


def _app_dir() -> pathlib.Path:
    global _APP_DIR
    if _APP_DIR is None:
        _APP_DIR = vault_root() / ".pensieve-app"
        _APP_DIR.mkdir(parents=True, exist_ok=True)
    return _APP_DIR


def _load() -> dict:
    p = _app_dir() / "preferences.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("preferences load failed: %s", e)
    return {}


def _save(data: dict) -> None:
    p = _app_dir() / "preferences.json"
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_prefs(user: str, action: str) -> dict:
    return _load().get(action, {}).get(user, {})


def save_prefs(user: str, action: str, prefs: dict) -> None:
    data = _load()
    data.setdefault(action, {})[user] = prefs
    _save(data)
