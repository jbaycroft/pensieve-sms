"""
tests/test_quick_actions.py — coverage for app.quick_actions
"""
import json
import pytest
import app.vault as vault_mod


@pytest.fixture(autouse=True)
def reset():
    vault_mod._VAULT_ROOT = None
    yield
    vault_mod._VAULT_ROOT = None


@pytest.fixture
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
    return tmp_path


# ── defaults ──────────────────────────────────────────────────────────────────

def test_get_actions_returns_defaults_when_no_file(vault):
    from app.quick_actions import get_actions, DEFAULTS
    assert get_actions() == DEFAULTS


def test_defaults_have_six_actions():
    from app.quick_actions import DEFAULTS
    assert len(DEFAULTS) == 6


def test_defaults_ids_are_unique():
    from app.quick_actions import DEFAULTS
    ids = [a["id"] for a in DEFAULTS]
    assert len(ids) == len(set(ids))


def test_all_defaults_have_required_fields():
    from app.quick_actions import DEFAULTS
    required = {"id", "icon", "label", "domain", "priority", "type"}
    for action in DEFAULTS:
        missing = required - set(action.keys())
        assert not missing, f"Action {action.get('id')} missing: {missing}"


def test_all_type_values_valid():
    from app.quick_actions import DEFAULTS
    valid_types = {"coffee", "prefilled", "freeform"}
    for action in DEFAULTS:
        assert action["type"] in valid_types, f"{action['id']} has invalid type {action['type']}"


# ── specific action assertions ─────────────────────────────────────────────────

def test_coffee_action_config():
    from app.quick_actions import DEFAULTS
    coffee = next(a for a in DEFAULTS if a["id"] == "coffee")
    assert coffee["type"] == "coffee"
    assert coffee["domain"] == "connection"
    assert coffee["icon"] == "☕"


def test_hydro_action_is_prefilled_with_task():
    from app.quick_actions import DEFAULTS
    hydro = next(a for a in DEFAULTS if a["id"] == "hydro")
    assert hydro["type"] == "prefilled"
    assert "task" in hydro
    assert "est_min" in hydro
    assert hydro["domain"] == "hydroponics"
    assert hydro["est_min"] == 15


def test_custom_action_has_null_domain():
    from app.quick_actions import DEFAULTS
    custom = next(a for a in DEFAULTS if a["id"] == "custom")
    assert custom["domain"] is None
    assert custom["type"] == "freeform"


def test_grocery_dogs_property_are_freeform():
    from app.quick_actions import DEFAULTS
    freeform_ids = {a["id"] for a in DEFAULTS if a["type"] == "freeform"}
    assert "grocery" in freeform_ids
    assert "dogs" in freeform_ids
    assert "property" in freeform_ids
    assert "custom" in freeform_ids


# ── custom file ───────────────────────────────────────────────────────────────

def test_get_actions_loads_custom_file(vault):
    from app.quick_actions import get_actions
    custom = [
        {"id": "test", "icon": "🧪", "label": "Test",
         "domain": "work", "priority": "normal", "type": "freeform"}
    ]
    app_dir = vault / ".pensieve-app"
    app_dir.mkdir(parents=True)
    (app_dir / "quick_actions.json").write_text(json.dumps(custom), encoding="utf-8")
    result = get_actions()
    assert len(result) == 1
    assert result[0]["id"] == "test"


def test_custom_file_overrides_defaults_completely(vault):
    from app.quick_actions import get_actions, DEFAULTS
    custom = [{"id": "x", "icon": "X", "label": "X", "domain": None,
               "priority": "normal", "type": "freeform"}]
    app_dir = vault / ".pensieve-app"
    app_dir.mkdir(parents=True)
    (app_dir / "quick_actions.json").write_text(json.dumps(custom), encoding="utf-8")
    result = get_actions()
    # Should NOT include any default IDs
    result_ids = {a["id"] for a in result}
    default_ids = {a["id"] for a in DEFAULTS}
    assert result_ids.isdisjoint(default_ids)


# ── fallback on bad file ───────────────────────────────────────────────────────

def test_invalid_json_falls_back_to_defaults(vault):
    from app.quick_actions import get_actions, DEFAULTS
    app_dir = vault / ".pensieve-app"
    app_dir.mkdir(parents=True)
    (app_dir / "quick_actions.json").write_text("NOT VALID JSON", encoding="utf-8")
    result = get_actions()
    assert result == DEFAULTS


def test_empty_json_array_returns_it(vault):
    from app.quick_actions import get_actions
    app_dir = vault / ".pensieve-app"
    app_dir.mkdir(parents=True)
    (app_dir / "quick_actions.json").write_text("[]", encoding="utf-8")
    # Empty list is valid JSON — should return it, not fall back
    result = get_actions()
    assert result == []
