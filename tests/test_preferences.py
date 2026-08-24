"""
tests/test_preferences.py — coverage for app.preferences
"""
import json
import pytest
import app.vault as vault_mod
import app.preferences as prefs_mod


@pytest.fixture(autouse=True)
def reset():
    vault_mod._VAULT_ROOT = None
    prefs_mod._APP_DIR = None
    yield
    vault_mod._VAULT_ROOT = None
    prefs_mod._APP_DIR = None


@pytest.fixture
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
    return tmp_path


# ── get_prefs ─────────────────────────────────────────────────────────────────

def test_get_prefs_returns_empty_when_no_file(vault):
    from app.preferences import get_prefs
    assert get_prefs("John", "coffee") == {}


def test_get_prefs_returns_empty_for_unknown_user(vault):
    from app.preferences import get_prefs, save_prefs
    save_prefs("John", "coffee", {"size": "large"})
    assert get_prefs("Jeannie", "coffee") == {}


def test_get_prefs_returns_empty_for_unknown_action(vault):
    from app.preferences import get_prefs, save_prefs
    save_prefs("John", "coffee", {"size": "large"})
    assert get_prefs("John", "grocery") == {}


# ── save_prefs ────────────────────────────────────────────────────────────────

def test_save_and_get_roundtrip(vault):
    from app.preferences import get_prefs, save_prefs
    save_prefs("John", "coffee", {"size": "large", "drink": "drip", "notes": "black"})
    result = get_prefs("John", "coffee")
    assert result["size"] == "large"
    assert result["drink"] == "drip"
    assert result["notes"] == "black"


def test_save_overwrites_existing(vault):
    from app.preferences import get_prefs, save_prefs
    save_prefs("John", "coffee", {"size": "small"})
    save_prefs("John", "coffee", {"size": "large"})
    assert get_prefs("John", "coffee")["size"] == "large"


def test_prefs_isolated_per_user(vault):
    from app.preferences import get_prefs, save_prefs
    save_prefs("John", "coffee", {"size": "large"})
    save_prefs("Jeannie", "coffee", {"size": "small", "drink": "latte"})
    assert get_prefs("John", "coffee")["size"] == "large"
    assert get_prefs("Jeannie", "coffee")["size"] == "small"
    assert get_prefs("Jeannie", "coffee")["drink"] == "latte"


def test_prefs_isolated_per_action(vault):
    from app.preferences import get_prefs, save_prefs
    save_prefs("John", "coffee", {"size": "large"})
    save_prefs("John", "grocery", {"store": "Whole Foods"})
    assert "store" not in get_prefs("John", "coffee")
    assert get_prefs("John", "grocery")["store"] == "Whole Foods"


def test_multiple_users_multiple_actions(vault):
    from app.preferences import get_prefs, save_prefs
    save_prefs("John", "coffee", {"size": "large", "drink": "drip"})
    save_prefs("Jeannie", "coffee", {"size": "medium", "drink": "latte", "notes": "oat milk"})
    save_prefs("John", "grocery", {"list": "milk, eggs"})

    assert get_prefs("John", "coffee")["drink"] == "drip"
    assert get_prefs("Jeannie", "coffee")["notes"] == "oat milk"
    assert get_prefs("John", "grocery")["list"] == "milk, eggs"
    assert get_prefs("Jeannie", "grocery") == {}


# ── file persistence ──────────────────────────────────────────────────────────

def test_prefs_persisted_to_json_file(vault):
    from app.preferences import save_prefs
    save_prefs("John", "coffee", {"size": "medium", "drink": "latte"})
    prefs_file = vault / ".pensieve-app" / "preferences.json"
    assert prefs_file.exists()
    data = json.loads(prefs_file.read_text())
    assert data["coffee"]["John"]["size"] == "medium"
    assert data["coffee"]["John"]["drink"] == "latte"


def test_app_dir_created_automatically(vault):
    from app.preferences import save_prefs
    app_dir = vault / ".pensieve-app"
    assert not app_dir.exists()
    save_prefs("John", "coffee", {"size": "large"})
    assert app_dir.exists()
    assert (app_dir / "preferences.json").exists()


def test_existing_file_preserved_on_update(vault):
    from app.preferences import get_prefs, save_prefs
    save_prefs("John", "coffee", {"size": "large"})
    save_prefs("Jeannie", "coffee", {"size": "small"})
    # John's prefs must survive Jeannie's save
    assert get_prefs("John", "coffee")["size"] == "large"
