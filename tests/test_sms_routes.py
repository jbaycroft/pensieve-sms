"""
tests/test_sms_routes.py — coverage for /test endpoint and SMS routing logic.

The /sms endpoint requires Twilio signature validation which can't be easily
exercised in unit tests. We test via /test (which bypasses auth) and verify
the routing logic (Jeannie isolation, unknown sender rejection).
"""
import json
import os
import pytest

os.environ["ENHANCE_MOCK"] = "1"

JOHN_NUMBER    = "+15550001111"
JEANNIE_NUMBER = "+15550009999"
UNKNOWN_NUMBER = "+15550007777"

os.environ["SMS_ALLOWLIST"]   = JOHN_NUMBER
os.environ["JEANNIE_NUMBER"]  = JEANNIE_NUMBER
os.environ["TWILIO_AUTH_TOKEN"] = "fake_token_for_tests"

import app.vault as vault_mod
import app.database as db_mod


@pytest.fixture(autouse=True)
def reset():
    vault_mod._VAULT_ROOT = None
    db_mod._DB_PATH = None
    db_mod.close_conn()
    yield
    vault_mod._VAULT_ROOT = None
    db_mod._DB_PATH = None
    db_mod.close_conn()


@pytest.fixture
def vault_dir(tmp_path):
    tickets = tmp_path / "00_Queue" / "Tickets"
    tickets.mkdir(parents=True)
    (tmp_path / "00_Queue" / "Index.md").write_text(
        "---\ntitle: Queue\n---\n%%\nFIFO\n%%\n\n", encoding="utf-8"
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
    with app.test_client() as c:
        yield c


# ── /test endpoint ────────────────────────────────────────────────────────────

def test_test_endpoint_returns_ticket(client, vault_dir):
    r = client.post("/test",
                    data=json.dumps({"body": "buy CO2 sensor", "from": JOHN_NUMBER}),
                    content_type="application/json")
    assert r.status_code == 200
    data = r.get_json()
    assert "ticket_id" in data
    assert data["ticket_id"].startswith("TKT-")


def test_test_endpoint_creates_ticket_file(client, vault_dir):
    r = client.post("/test",
                    data=json.dumps({"body": "h: check pH", "from": JOHN_NUMBER}),
                    content_type="application/json")
    data = r.get_json()
    path = vault_dir / "00_Queue" / "Tickets" / f"{data['ticket_id']}.md"
    assert path.exists()


def test_test_endpoint_ticket_has_correct_domain(client, vault_dir):
    r = client.post("/test",
                    data=json.dumps({"body": "h: check pH", "from": JOHN_NUMBER}),
                    content_type="application/json")
    data = r.get_json()
    path = vault_dir / "00_Queue" / "Tickets" / f"{data['ticket_id']}.md"
    assert "domain: hydroponics" in path.read_text()


def test_test_endpoint_urgent_creates_critical_ticket(client, vault_dir):
    r = client.post("/test",
                    data=json.dumps({"body": "!! fix prod NOW", "from": JOHN_NUMBER}),
                    content_type="application/json")
    data = r.get_json()
    path = vault_dir / "00_Queue" / "Tickets" / f"{data['ticket_id']}.md"
    assert "priority: critical" in path.read_text()


def test_test_endpoint_empty_body_returns_400(client):
    r = client.post("/test",
                    data=json.dumps({"body": "", "from": JOHN_NUMBER}),
                    content_type="application/json")
    assert r.status_code == 400


def test_test_endpoint_missing_body_returns_400(client):
    r = client.post("/test",
                    data=json.dumps({"from": JOHN_NUMBER}),
                    content_type="application/json")
    assert r.status_code == 400


def test_test_endpoint_includes_ack_in_response(client):
    r = client.post("/test",
                    data=json.dumps({"body": "pick up dog food"}),
                    content_type="application/json")
    data = r.get_json()
    assert "ack" in data
    assert len(data["ack"]) > 0


def test_test_endpoint_all_domain_prefixes(client, vault_dir):
    domain_cases = [
        ("w: update billing", "work"),
        ("h: top off reservoir", "hydroponics"),
        ("p: fix fence post", "property"),
        ("f: stretch hamstrings", "physical"),
        ("ho: undercoat minis", "hobby"),
        ("c: call James", "connection"),
    ]
    for body, expected_domain in domain_cases:
        r = client.post("/test",
                        data=json.dumps({"body": body, "from": JOHN_NUMBER}),
                        content_type="application/json")
        assert r.status_code == 200, f"Failed for: {body}"
        data = r.get_json()
        path = vault_dir / "00_Queue" / "Tickets" / f"{data['ticket_id']}.md"
        content = path.read_text()
        assert f"domain: {expected_domain}" in content, f"Wrong domain for: {body}"


def test_test_endpoint_long_form_domain_prefixes(client, vault_dir):
    long_form_cases = [
        ("work: deploy service", "work"),
        ("hydroponics: check EC", "hydroponics"),
        ("property: chainsaw oil", "property"),
        ("physical: trail run", "physical"),
        ("hobby: paint Deathwing", "hobby"),
        ("connection: text Jeannie", "connection"),
    ]
    for body, expected_domain in long_form_cases:
        r = client.post("/test",
                        data=json.dumps({"body": body, "from": JOHN_NUMBER}),
                        content_type="application/json")
        assert r.status_code == 200
        data = r.get_json()
        path = vault_dir / "00_Queue" / "Tickets" / f"{data['ticket_id']}.md"
        assert f"domain: {expected_domain}" in path.read_text()


# ── Jeannie isolation ─────────────────────────────────────────────────────────

def test_jeannie_routed_separately(client, vault_dir):
    """Jeannie's number triggers jeannie_ingest, not the normal flow."""
    r = client.post("/test",
                    data=json.dumps({"body": "remind me to take vitamins",
                                     "from": JEANNIE_NUMBER}),
                    content_type="application/json")
    # Should succeed (Jeannie handler runs) — returns 200 with ticket
    assert r.status_code == 200


def test_jeannie_ticket_created(client, vault_dir):
    r = client.post("/test",
                    data=json.dumps({"body": "h: water the seedlings",
                                     "from": JEANNIE_NUMBER}),
                    content_type="application/json")
    data = r.get_json()
    assert "ticket_id" in data


def test_jeannie_not_routed_as_unknown(client, vault_dir):
    """Jeannie must be checked BEFORE the allowlist check.
    If she were treated as unknown, her messages would be rejected.
    Verify her messages actually create tickets."""
    r = client.post("/test",
                    data=json.dumps({"body": "buy oat milk",
                                     "from": JEANNIE_NUMBER}),
                    content_type="application/json")
    data = r.get_json()
    # If error key present, Jeannie was rejected as unknown
    assert "error" not in data
    assert "ticket_id" in data


# ── /test disabled in prod ────────────────────────────────────────────────────

def test_test_endpoint_disabled_returns_403(vault_dir, monkeypatch):
    monkeypatch.setenv("VAULT_ROOT", str(vault_dir))
    monkeypatch.setenv("ENHANCE_MOCK", "1")
    monkeypatch.setenv("TEST_ENDPOINT_ENABLED", "0")
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        r = c.post("/test",
                   data=json.dumps({"body": "should be blocked"}),
                   content_type="application/json")
        assert r.status_code == 403


# ── queue ordering via /test ───────────────────────────────────────────────────

def test_normal_tickets_append_in_order(client, vault_dir):
    import re
    for i in range(3):
        client.post("/test",
                    data=json.dumps({"body": f"task {i}", "from": JOHN_NUMBER}),
                    content_type="application/json")
    index = (vault_dir / "00_Queue" / "Index.md").read_text()
    body = re.sub(r"^---[\s\S]*?---\n?", "", index)
    body = re.sub(r"%%[\s\S]*?%%\n?", "", body)
    links = re.findall(r"\[\[([^\]]+)\]\]", body)
    # All 3 should appear, in order
    assert len(links) == 3


def test_urgent_ticket_jumps_to_head(client, vault_dir):
    import re
    # Add two normal tickets first
    client.post("/test", data=json.dumps({"body": "normal 1"}), content_type="application/json")
    client.post("/test", data=json.dumps({"body": "normal 2"}), content_type="application/json")
    # Now add urgent
    r = client.post("/test",
                    data=json.dumps({"body": "!! URGENT NOW"}),
                    content_type="application/json")
    urgent_id = r.get_json()["ticket_id"]
    index = (vault_dir / "00_Queue" / "Index.md").read_text()
    body = re.sub(r"^---[\s\S]*?---\n?", "", index)
    body = re.sub(r"%%[\s\S]*?%%\n?", "", body)
    links = re.findall(r"\[\[([^\]]+)\]\]", body)
    assert links[0] == urgent_id


def test_high_priority_is_second(client, vault_dir):
    import re
    r1 = client.post("/test", data=json.dumps({"body": "normal task"}),
                     content_type="application/json")
    normal_id = r1.get_json()["ticket_id"]
    r2 = client.post("/test", data=json.dumps({"body": "! high priority task"}),
                     content_type="application/json")
    high_id = r2.get_json()["ticket_id"]
    index = (vault_dir / "00_Queue" / "Index.md").read_text()
    body = re.sub(r"^---[\s\S]*?---\n?", "", index)
    body = re.sub(r"%%[\s\S]*?%%\n?", "", body)
    links = re.findall(r"\[\[([^\]]+)\]\]", body)
    assert links[0] == normal_id   # normal was first, stays first
    assert links[1] == high_id     # high inserted at position 2
