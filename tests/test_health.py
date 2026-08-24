"""tests/test_health.py — /health and /health/db endpoint tests."""
import pytest
import app.database as db_mod
import app.vault as vault_mod


@pytest.fixture(autouse=True)
def reset(tmp_path, monkeypatch):
    vault_mod._VAULT_ROOT = None
    db_mod._DB_PATH = None
    db_mod.close_conn()
    monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
    # Create Index.md so vault_ok check passes
    (tmp_path / "00_Queue" / "Tickets").mkdir(parents=True)
    (tmp_path / "00_Queue" / "Index.md").write_text("---\ntitle: Queue\n---\n")
    db_mod._DB_PATH = tmp_path / ".pensieve-app" / "pensieve.db"
    db_mod._DB_PATH.parent.mkdir(parents=True)
    db_mod.init_db()
    yield
    vault_mod._VAULT_ROOT = None
    db_mod._DB_PATH = None
    db_mod.close_conn()


@pytest.fixture()
def client(reset):
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ── /health ───────────────────────────────────────────────────────────────────

def test_health_returns_200(client):
    r = client.get("/health")
    assert r.status_code == 200


def test_health_json_shape(client):
    r = client.get("/health")
    d = r.get_json()
    assert "status" in d
    assert "db_ok" in d
    assert "vault_ok" in d
    assert "queue_depth" in d
    assert "uptime_s" in d
    assert "version" in d


def test_health_status_ok_when_configured(client):
    r = client.get("/health")
    d = r.get_json()
    assert d["db_ok"] is True
    assert d["vault_ok"] is True
    assert d["status"] == "ok"


def test_health_queue_depth_empty(client):
    r = client.get("/health")
    assert r.get_json()["queue_depth"] == 0


def test_health_queue_depth_reflects_seeded_ticket(client):
    from app.vault import write_ticket, write_index
    tid = write_ticket("Test task", "work", "normal", 30)
    write_index(tid, "normal")
    r = client.get("/health")
    assert r.get_json()["queue_depth"] == 1


def test_health_vault_not_ok_when_index_missing(tmp_path, monkeypatch):
    """If Index.md is absent, vault_ok should be False and status degraded."""
    # Use a fresh vault without Index.md
    vault2 = tmp_path / "empty_vault"
    vault2.mkdir()
    monkeypatch.setenv("VAULT_ROOT", str(vault2))

    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        r = c.get("/health")
        d = r.get_json()
        assert d["vault_ok"] is False
        assert d["status"] == "degraded"
        assert r.status_code == 503


# ── /health/db ────────────────────────────────────────────────────────────────

def test_health_db_returns_200(client):
    r = client.get("/health/db")
    assert r.status_code == 200


def test_health_db_json_shape(client):
    d = client.get("/health/db").get_json()
    assert "tables" in d
    assert "integrity" in d
    assert d["integrity"] == "ok"


def test_health_db_shows_ticket_count(client):
    from app.vault import write_ticket, write_index
    write_ticket("Count me", "work", "normal", 30)
    d = client.get("/health/db").get_json()
    assert d["tables"]["tickets"] == 1


# ── security headers ──────────────────────────────────────────────────────────

def test_security_headers_present(client):
    r = client.get("/health")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert "Content-Security-Policy" in r.headers
    assert r.headers.get("Referrer-Policy") == "same-origin"