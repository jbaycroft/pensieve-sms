"""quick_actions.py — configurable quick action button definitions.
Defaults built-in. Override via VAULT_ROOT/.pensieve-app/quick_actions.json
"""
import json
import logging
from .vault import vault_root

log = logging.getLogger(__name__)

DEFAULTS = [
    {"id": "coffee",   "icon": "☕", "label": "Coffee",      "domain": "connection",  "priority": "month", "type": "coffee"},
    {"id": "grocery",  "icon": "🛒", "label": "Grocery",     "domain": "property",    "priority": "month", "type": "freeform"},
    {"id": "hydro",    "icon": "🌱", "label": "Hydro Check", "domain": "hydroponics", "priority": "month", "type": "prefilled",
     "task": "Check pH / EC / water level", "est_min": 15},
    {"id": "dogs",     "icon": "🐕", "label": "Dogs",        "domain": "property",    "priority": "month", "type": "freeform"},
    {"id": "property", "icon": "🔧", "label": "Property",    "domain": "property",    "priority": "month", "type": "freeform"},
    {"id": "custom",   "icon": "✏️",  "label": "Custom",     "domain": None,          "priority": "month", "type": "freeform"},
]


def get_actions() -> list:
    try:
        path = vault_root() / ".pensieve-app" / "quick_actions.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("quick_actions load failed: %s — using defaults", e)
    return DEFAULTS
