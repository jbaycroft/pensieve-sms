"""
tests/test_pwa.py — comprehensive coverage of app.routes.pwa

All tests use ENHANCE_MOCK=1 (no Gemini calls).
Vault is a tmp_path with the required Index.md structure.
"""
import json
import os
import pytest

os.environ["ENHANCE_MOCK"] = "1"
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test_token")
os.environ.setdefault("SMS_ALLOWLIST", "+15550001111")
os.environ.setdefault("JEANNIE_NUMBER", "+15550009999")

import app.vault as vault_mod
import app.preferences as prefs_mod
import app.database as db_mod


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_modules():
    vault_mod._VAULT_ROOT = None
    prefs_mod._APP_DIR = None
    db_mod._DB_PATH = None
    db_mod.close_conn()
    yield
    vault_mod._VAULT_ROOT = None
    prefs_mod._APP_DIR = None
    db_mod._DB_PATH = None
    db_mod.close_conn()


@pytest.fixture
def vault_dir(tmp_path):
    tickets = tmp_path / "00_Queue" / "Tickets"
    tickets.mkdir(parents=True)
    index = tmp_path / "00_Queue" / "Index.md"
    index.write_text(
        "---\ntitle: Queue\ndescription: FIFO queue [[TKT-*]]\n---\n"
        "%%\nHEAD: first [[TKT-*]]\n%%\n\n[[TKT-EXISTING]]\n",
        encoding="utf-8",
    )
    # Write a fake existing ticket .md (Obsidian display layer)
    (tickets / "TKT-EXISTING.md").write_text(
        "---\nid: TKT-EXISTING\ntitle: Existing task\ndomain: work\n"
        "priority: normal\nstatus: queued\ncreated: 2026-08-23\n"
        "energy: medium\nest_min: 30\nrecur: false\nsource: sms\ntags: [work]\n---\n\nExisting task\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def client(vault_dir, monkeypatch):
    monkeypatch.setenv("VAULT_ROOT", str(vault_dir))
    monkeypatch.setenv("ENHANCE_MOCK", "1")
    monkeypatch.setenv("TEST_ENDPOINT_ENABLED", "1")
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    # Seed DB with the existing ticket from vault_dir fixture
    db_mod.create_ticket("TKT-EXISTING", "Existing task", "work", "normal")
    db_mod.enqueue_ticket("TKT-EXISTING", "normal")
    with app.test_client() as c:
        yield c


# ── home page ─────────────────────────────────────────────────────────────────

def test_home_returns_200(client):
    r = client.get("/")
    assert r.status_code == 200


def test_home_content_type_is_html(client):
    r = client.get("/")
    assert "text/html" in r.content_type


def test_home_contains_burrow_title(client):
    r = client.get("/")
    assert b"The Burrow" in r.data


def test_home_contains_quick_action_buttons(client):
    r = client.get("/")
    html = r.data
    assert b"Coffee" in html
    assert b"Grocery" in html
    assert b"Hydro" in html
    assert b"Dogs" in html


def test_home_contains_greeting_names(client):
    """User names appear in greeting text (auto-detected from Google auth)."""
    r = client.get("/")
    assert b"John" in r.data
    assert b"Jeannie" in r.data


def test_home_contains_htmx_queue_element(client):
    r = client.get("/")
    assert b"queue-list" in r.data


# ── queue partial ─────────────────────────────────────────────────────────────

def test_queue_returns_200(client):
    r = client.get("/api/queue")
    assert r.status_code == 200


def test_queue_shows_existing_ticket(client):
    r = client.get("/api/queue")
    assert b"Existing task" in r.data


def test_queue_shows_head_badge_on_first(client):
    r = client.get("/api/queue")
    assert b"HEAD" in r.data


def test_queue_empty_when_no_tickets(client):
    # Close the pre-seeded ticket so the DB queue is empty
    db_mod.close_ticket("TKT-EXISTING")
    r = client.get("/api/queue")
    assert r.status_code == 200
    assert b"Quest log is empty" in r.data


# ── action panels ─────────────────────────────────────────────────────────────

def test_coffee_panel_returns_200(client):
    r = client.get("/api/action-panel/coffee?user=John")
    assert r.status_code == 200


def test_coffee_panel_contains_size_options(client):
    r = client.get("/api/action-panel/coffee?user=John")
    html = r.data
    assert b"small" in html
    assert b"medium" in html
    assert b"large" in html


def test_coffee_panel_contains_drink_options(client):
    r = client.get("/api/action-panel/coffee?user=John")
    html = r.data
    assert b"drip" in html
    assert b"latte" in html
    assert b"espresso" in html


def test_coffee_panel_contains_remember_checkbox(client):
    r = client.get("/api/action-panel/coffee?user=John")
    assert b"Remember" in r.data


def test_coffee_panel_prefills_saved_preferences(client, vault_dir, monkeypatch):
    monkeypatch.setenv("VAULT_ROOT", str(vault_dir))
    from app.preferences import save_prefs
    save_prefs("Jeannie", "coffee", {"size": "medium", "drink": "latte", "notes": "oat milk"})
    r = client.get("/api/action-panel/coffee?user=Jeannie")
    html = r.data.decode()
    assert "oat milk" in html


def test_hydro_panel_shows_task_text(client):
    r = client.get("/api/action-panel/hydro?user=John")
    assert r.status_code == 200
    assert b"pH" in r.data or b"Check" in r.data


def test_grocery_panel_shows_input(client):
    r = client.get("/api/action-panel/grocery?user=John")
    assert r.status_code == 200
    # Freeform panel has a text input
    assert b"input" in r.data or b"Queue it" in r.data


def test_unknown_action_panel_returns_404(client):
    r = client.get("/api/action-panel/nonexistent")
    assert r.status_code == 404


# ── POST /api/task ────────────────────────────────────────────────────────────

def test_add_task_plain_text(client, vault_dir):
    r = client.post("/api/task",
                    data=json.dumps({"body": "buy CO2 sensor"}),
                    content_type="application/json")
    assert r.status_code == 200
    data = r.get_json()
    assert "ticket_id" in data
    assert data["ticket_id"].startswith("TKT-")
    assert "ack" in data
    assert "enhanced" in data


def test_add_task_creates_ticket_file(client, vault_dir):
    r = client.post("/api/task",
                    data=json.dumps({"body": "h: check pH levels"}),
                    content_type="application/json")
    data = r.get_json()
    ticket_path = vault_dir / "00_Queue" / "Tickets" / f"{data['ticket_id']}.md"
    assert ticket_path.exists()


def test_add_task_with_priority_prefix(client, vault_dir):
    r = client.post("/api/task",
                    data=json.dumps({"body": "!! fix staging now"}),
                    content_type="application/json")
    assert r.status_code == 200
    data = r.get_json()
    ticket_path = vault_dir / "00_Queue" / "Tickets" / f"{data['ticket_id']}.md"
    assert "priority: critical" in ticket_path.read_text()


def test_add_task_urgent_becomes_head(client, vault_dir):
    r = client.post("/api/task",
                    data=json.dumps({"body": "!! emergency fix"}),
                    content_type="application/json")
    data = r.get_json()
    index = (vault_dir / "00_Queue" / "Index.md").read_text()
    # Find the first [[...]] link after the %% block
    import re
    body = re.sub(r"^---[\s\S]*?---\n?", "", index)
    body = re.sub(r"%%[\s\S]*?%%\n?", "", body)
    links = re.findall(r"\[\[([^\]]+)\]\]", body)
    assert links[0] == data["ticket_id"]


def test_add_task_empty_body_returns_400(client):
    r = client.post("/api/task",
                    data=json.dumps({"body": ""}),
                    content_type="application/json")
    assert r.status_code == 400


def test_add_task_missing_body_returns_400(client):
    r = client.post("/api/task",
                    data=json.dumps({}),
                    content_type="application/json")
    assert r.status_code == 400


def test_add_task_domain_prefix_respected(client, vault_dir):
    r = client.post("/api/task",
                    data=json.dumps({"body": "h: top off reservoir"}),
                    content_type="application/json")
    data = r.get_json()
    ticket_path = vault_dir / "00_Queue" / "Tickets" / f"{data['ticket_id']}.md"
    assert "domain: hydroponics" in ticket_path.read_text()


# ── POST /api/quick-action ────────────────────────────────────────────────────

def test_coffee_quick_action(client, vault_dir):
    r = client.post("/api/quick-action",
                    data=json.dumps({
                        "action_id": "coffee", "user": "John",
                        "size": "large", "drink": "drip", "notes": "black",
                        "remember": False,
                    }),
                    content_type="application/json")
    assert r.status_code == 200
    data = r.get_json()
    assert "ticket_id" in data
    assert "large" in data["enhanced"] or "drip" in data["enhanced"]


def test_coffee_quick_action_creates_connection_ticket(client, vault_dir):
    r = client.post("/api/quick-action",
                    data=json.dumps({
                        "action_id": "coffee", "user": "Jeannie",
                        "size": "medium", "drink": "latte", "notes": "oat milk",
                        "remember": False,
                    }),
                    content_type="application/json")
    data = r.get_json()
    ticket_path = vault_dir / "00_Queue" / "Tickets" / f"{data['ticket_id']}.md"
    content = ticket_path.read_text()
    assert "domain: connection" in content


def test_coffee_remember_saves_preferences(client, vault_dir, monkeypatch):
    monkeypatch.setenv("VAULT_ROOT", str(vault_dir))
    client.post("/api/quick-action",
                data=json.dumps({
                    "action_id": "coffee", "user": "Jeannie",
                    "size": "medium", "drink": "latte", "notes": "oat milk",
                    "remember": True,
                }),
                content_type="application/json")
    from app.preferences import get_prefs
    saved = get_prefs("Jeannie", "coffee")
    assert saved["size"] == "medium"
    assert saved["drink"] == "latte"
    assert saved["notes"] == "oat milk"


def test_coffee_no_remember_does_not_save(client, vault_dir, monkeypatch):
    monkeypatch.setenv("VAULT_ROOT", str(vault_dir))
    client.post("/api/quick-action",
                data=json.dumps({
                    "action_id": "coffee", "user": "John",
                    "size": "small", "drink": "americano",
                    "remember": False,
                }),
                content_type="application/json")
    from app.preferences import get_prefs
    saved = get_prefs("John", "coffee")
    assert saved == {}  # nothing saved


def test_hydro_prefilled_action(client, vault_dir):
    r = client.post("/api/quick-action",
                    data=json.dumps({"action_id": "hydro", "user": "John"}),
                    content_type="application/json")
    assert r.status_code == 200
    data = r.get_json()
    assert "ticket_id" in data
    ticket_path = vault_dir / "00_Queue" / "Tickets" / f"{data['ticket_id']}.md"
    content = ticket_path.read_text()
    assert "domain: hydroponics" in content
    assert "est_min: 15" in content


def test_freeform_action_with_body(client, vault_dir):
    r = client.post("/api/quick-action",
                    data=json.dumps({
                        "action_id": "grocery", "user": "John",
                        "body": "pick up dog food and milk",
                    }),
                    content_type="application/json")
    assert r.status_code == 200
    data = r.get_json()
    assert "ticket_id" in data


def test_freeform_action_without_body_returns_400(client):
    r = client.post("/api/quick-action",
                    data=json.dumps({"action_id": "grocery", "user": "John", "body": ""}),
                    content_type="application/json")
    assert r.status_code == 400


def test_unknown_action_returns_400(client):
    r = client.post("/api/quick-action",
                    data=json.dumps({"action_id": "nonexistent", "user": "John"}),
                    content_type="application/json")
    assert r.status_code == 400


# ── preferences API ───────────────────────────────────────────────────────────

def test_get_preferences_empty(client):
    r = client.get("/api/preferences/John/coffee")
    assert r.status_code == 200
    assert r.get_json() == {}


def test_set_and_get_preferences(client):
    prefs = {"size": "large", "drink": "drip", "notes": "black"}
    client.post("/api/preferences/John/coffee",
                data=json.dumps(prefs), content_type="application/json")
    r = client.get("/api/preferences/John/coffee")
    data = r.get_json()
    assert data["size"] == "large"
    assert data["drink"] == "drip"


def test_preferences_isolated_per_user_via_api(client):
    client.post("/api/preferences/John/coffee",
                data=json.dumps({"size": "large"}), content_type="application/json")
    client.post("/api/preferences/Jeannie/coffee",
                data=json.dumps({"size": "small"}), content_type="application/json")
    assert client.get("/api/preferences/John/coffee").get_json()["size"] == "large"
    assert client.get("/api/preferences/Jeannie/coffee").get_json()["size"] == "small"


# ── PWA manifest ──────────────────────────────────────────────────────────────

def test_manifest_returns_200(client):
    r = client.get("/manifest.json")
    assert r.status_code == 200


def test_manifest_is_valid_pwa(client):
    data = client.get("/manifest.json").get_json()
    assert data["name"] == "The Burrow"
    assert data["display"] == "standalone"
    assert "icons" in data
    assert len(data["icons"]) >= 1
    assert "start_url" in data
    assert "theme_color" in data


def test_manifest_content_type_is_json(client):
    r = client.get("/manifest.json")
    assert "application/json" in r.content_type


# ── service worker ────────────────────────────────────────────────────────────

def test_sw_js_returns_200(client):
    r = client.get("/sw.js")
    assert r.status_code == 200


def test_sw_js_is_javascript(client):
    r = client.get("/sw.js")
    assert b"self.addEventListener" in r.data or b"caches" in r.data


# -- input validation -----------------------------------------------------------

def test_add_task_body_over_500_returns_400(client):
    r = client.post('/api/task', json={'body': 'b' * 501})
    assert r.status_code == 400
    assert b'exceeds' in r.data


def test_quick_action_invalid_action_id_returns_400(client):
    r = client.post('/api/quick-action', json={'action_id': '../../../etc/passwd', 'user': 'John'})
    assert r.status_code == 400
    assert b'invalid action_id' in r.data


def test_quick_action_invalid_user_returns_400(client):
    r = client.post('/api/quick-action', json={'action_id': 'coffee', 'user': '<script>alert(1)</script>'})
    assert r.status_code == 400
    assert b'invalid user' in r.data


def test_quick_action_empty_action_id_returns_400(client):
    r = client.post('/api/quick-action', json={'action_id': '', 'user': 'John'})
    assert r.status_code == 400


# ── complete task ─────────────────────────────────────────────────────────────

def test_complete_task_removes_from_queue(client):
    """POST /api/task/<id>/done should mark the ticket done and remove it from the queue."""
    # Verify ticket exists in queue first
    r = client.get('/api/queue')
    assert b'TKT-EXISTING' in r.data or b'Existing task' in r.data

    r = client.post('/api/task/TKT-EXISTING/done', json={})
    assert r.status_code == 200
    data = r.get_json()
    assert data['ok'] is True
    assert data['ticket_id'] == 'TKT-EXISTING'

    # Queue should now be empty
    r = client.get('/api/queue')
    assert b'Existing task' not in r.data


def test_complete_task_invalid_id_returns_400(client):
    r = client.post('/api/task/../../../etc/passwd/done', json={})
    assert r.status_code in (400, 404)


def test_complete_task_updates_ticket_status(client):
    """After completion, the ticket should have status='done' in the database."""
    client.post('/api/task/TKT-EXISTING/done', json={})
    ticket = db_mod.get_ticket('TKT-EXISTING')
    assert ticket is not None
    assert ticket['status'] == 'done'
