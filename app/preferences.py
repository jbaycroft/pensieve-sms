"""preferences.py — per-user, per-action preference store.

Backed by SQLite (app/database.py) — preferences table.
Public interface is unchanged: get_prefs(user, action) / save_prefs(user, action, prefs).

_APP_DIR is kept as a module-level sentinel for backward-compatible test reset only.
"""
import logging
from . import database

log = logging.getLogger(__name__)

# Kept for test fixture compatibility (reset between tests)
_APP_DIR = None


def get_prefs(user: str, action: str) -> dict:
    """Return saved preferences for (user, action), or {} if none."""
    return database.get_prefs(user, action)


def save_prefs(user: str, action: str, prefs: dict) -> None:
    """Persist preferences for (user, action)."""
    database.save_prefs(user, action, prefs)

