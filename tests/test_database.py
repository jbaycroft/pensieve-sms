"""
tests/test_database.py — SQLite data layer (app/database.py)
"""
import pytest
import app.vault as vault_mod
import app.database as db


@pytest.fixture(autouse=True)
def reset():
    vault_mod._VAULT_ROOT = None
    db._DB_PATH = None
    db.close_conn()
    yield
    vault_mod._VAULT_ROOT = None
    db._DB_PATH = None
    db.close_conn()


@pytest.fixture
def vault(tmp_path, monkeypatch):
    (tmp_path / "00_Queue" / "Tickets").mkdir(parents=True)
    (tmp_path / "00_Queue" / "Index.md").write_text(
        "---\ntitle: Queue\n---\n%%\nFIFO\n%%\n\n", encoding="utf-8"
    )
    monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
    db.init_db()
    return tmp_path


# ── init_db ───────────────────────────────────────────────────────────────────

def test_init_db_creates_tables(vault):
    conn = db.get_conn()
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "tickets"    in tables
    assert "queue_order" in tables
    assert "preferences" in tables
    assert "audit_log"  in tables
    assert "people"     in tables


def test_init_db_is_idempotent(vault):
    db.init_db()
    db.init_db()  # should not raise or duplicate tables


# ── create_ticket ─────────────────────────────────────────────────────────────

def test_create_ticket_inserts_row(vault):
    db.create_ticket("TKT-001", "Buy CO2 sensor", "hydroponics", "normal")
    row = db.get_conn().execute(
        "SELECT * FROM tickets WHERE id='TKT-001'"
    ).fetchone()
    assert row is not None
    assert row["title"] == "Buy CO2 sensor"
    assert row["domain"] == "hydroponics"
    assert row["priority"] == "normal"
    assert row["status"] == "queued"
    assert row["source"] == "sms"


def test_create_ticket_default_est_min(vault):
    db.create_ticket("TKT-002", "Task", "work", "normal")
    row = db.get_conn().execute("SELECT est_min FROM tickets WHERE id='TKT-002'").fetchone()
    assert row["est_min"] == 30


def test_create_ticket_custom_est_min(vault):
    db.create_ticket("TKT-003", "Task", "work", "normal", est_min=15)
    row = db.get_conn().execute("SELECT est_min FROM tickets WHERE id='TKT-003'").fetchone()
    assert row["est_min"] == 15


def test_create_ticket_ignore_duplicate(vault):
    db.create_ticket("TKT-DUP", "First", "work", "normal")
    db.create_ticket("TKT-DUP", "Second", "work", "normal")  # should not raise
    count = db.get_conn().execute(
        "SELECT COUNT(*) FROM tickets WHERE id='TKT-DUP'"
    ).fetchone()[0]
    assert count == 1


def test_create_ticket_logs_audit(vault):
    db.create_ticket("TKT-AUDIT", "Audited task", "work", "normal")
    logs = db.get_audit_log("TKT-AUDIT")
    assert len(logs) >= 1
    assert logs[0]["action"] == "create_ticket"
    assert logs[0]["ticket_id"] == "TKT-AUDIT"


# ── enqueue_ticket ────────────────────────────────────────────────────────────

def test_enqueue_normal_appends_to_tail(vault):
    for i in range(3):
        db.create_ticket(f"TKT-N{i}", f"Task {i}", "work", "normal")
        db.enqueue_ticket(f"TKT-N{i}", "normal")
    queue = db.get_queue()
    assert [t["id"] for t in queue] == ["TKT-N0", "TKT-N1", "TKT-N2"]


def test_enqueue_urgent_becomes_head(vault):
    db.create_ticket("TKT-A", "Normal A", "work", "normal")
    db.enqueue_ticket("TKT-A", "normal")
    db.create_ticket("TKT-B", "Normal B", "work", "normal")
    db.enqueue_ticket("TKT-B", "normal")

    db.create_ticket("TKT-URG", "Urgent", "work", "urgent")
    db.enqueue_ticket("TKT-URG", "urgent")

    queue = db.get_queue()
    assert queue[0]["id"] == "TKT-URG"
    assert len(queue) == 3


def test_enqueue_high_inserts_at_position_2(vault):
    db.create_ticket("TKT-A", "Normal A", "work", "normal")
    db.enqueue_ticket("TKT-A", "normal")
    db.create_ticket("TKT-B", "Normal B", "work", "normal")
    db.enqueue_ticket("TKT-B", "normal")

    db.create_ticket("TKT-HI", "High", "work", "high")
    db.enqueue_ticket("TKT-HI", "high")

    queue = db.get_queue()
    assert queue[0]["id"] == "TKT-A"
    assert queue[1]["id"] == "TKT-HI"
    assert queue[2]["id"] == "TKT-B"


def test_enqueue_high_with_empty_queue_goes_to_position_2(vault):
    """High with no existing items: falls back to enqueuing at position 2 (same as 1 effectively)."""
    db.create_ticket("TKT-HI", "High solo", "work", "high")
    db.enqueue_ticket("TKT-HI", "high")
    queue = db.get_queue()
    assert queue[0]["id"] == "TKT-HI"


def test_multiple_urgent_ordering(vault):
    db.create_ticket("TKT-A", "First", "work", "urgent")
    db.enqueue_ticket("TKT-A", "urgent")
    db.create_ticket("TKT-B", "Second urgent", "work", "urgent")
    db.enqueue_ticket("TKT-B", "urgent")

    queue = db.get_queue()
    assert queue[0]["id"] == "TKT-B"  # most recent urgent is HEAD
    assert queue[1]["id"] == "TKT-A"


# ── get_queue ─────────────────────────────────────────────────────────────────

def test_get_queue_empty(vault):
    assert db.get_queue() == []


def test_get_queue_returns_correct_fields(vault):
    db.create_ticket("TKT-QQ", "Check pH", "hydroponics", "normal", est_min=15)
    db.enqueue_ticket("TKT-QQ", "normal")
    queue = db.get_queue()
    assert len(queue) == 1
    t = queue[0]
    assert t["id"] == "TKT-QQ"
    assert t["title"] == "Check pH"
    assert t["domain"] == "hydroponics"
    assert t["priority"] == "normal"
    assert t["est_min"] == 15
    assert t["status"] == "queued"


def test_get_queue_respects_limit(vault):
    for i in range(10):
        db.create_ticket(f"TKT-L{i}", f"Task {i}", "work", "normal")
        db.enqueue_ticket(f"TKT-L{i}", "normal")
    queue = db.get_queue(limit=5)
    assert len(queue) == 5


def test_get_queue_excludes_done_tickets(vault):
    db.create_ticket("TKT-DONE", "Done task", "work", "normal")
    db.enqueue_ticket("TKT-DONE", "normal")
    db.close_ticket("TKT-DONE")
    assert db.get_queue() == []


# ── close_ticket ──────────────────────────────────────────────────────────────

def test_close_ticket_sets_status_done(vault):
    db.create_ticket("TKT-CLO", "Task", "work", "normal")
    db.enqueue_ticket("TKT-CLO", "normal")
    db.close_ticket("TKT-CLO")
    row = db.get_conn().execute(
        "SELECT status, completed_at FROM tickets WHERE id='TKT-CLO'"
    ).fetchone()
    assert row["status"] == "done"
    assert row["completed_at"] is not None


def test_close_ticket_removes_from_queue(vault):
    db.create_ticket("TKT-CLO2", "Task", "work", "normal")
    db.enqueue_ticket("TKT-CLO2", "normal")
    db.close_ticket("TKT-CLO2")
    assert db.get_queue() == []


def test_close_ticket_compacts_positions(vault):
    for i in range(3):
        db.create_ticket(f"TKT-C{i}", f"Task {i}", "work", "normal")
        db.enqueue_ticket(f"TKT-C{i}", "normal")
    db.close_ticket("TKT-C1")
    positions = [r[0] for r in db.get_conn().execute(
        "SELECT position FROM queue_order ORDER BY position"
    ).fetchall()]
    assert positions == [1, 2]


def test_close_ticket_logs_audit(vault):
    db.create_ticket("TKT-CAUD", "Task", "work", "normal")
    db.enqueue_ticket("TKT-CAUD", "normal")
    db.close_ticket("TKT-CAUD", actor="john")
    logs = db.get_audit_log("TKT-CAUD")
    actions = [l["action"] for l in logs]
    assert "close_ticket" in actions
    close_log = next(l for l in logs if l["action"] == "close_ticket")
    import json
    assert json.loads(close_log["detail_json"])["actor"] == "john"


# ── preferences ───────────────────────────────────────────────────────────────

def test_get_prefs_empty(vault):
    assert db.get_prefs("John", "coffee") == {}


def test_save_and_get_prefs_roundtrip(vault):
    db.save_prefs("John", "coffee", {"size": "large", "drink": "drip"})
    result = db.get_prefs("John", "coffee")
    assert result["size"] == "large"
    assert result["drink"] == "drip"


def test_prefs_isolated_per_user(vault):
    db.save_prefs("John", "coffee", {"size": "large"})
    db.save_prefs("Jeannie", "coffee", {"size": "small"})
    assert db.get_prefs("John", "coffee")["size"] == "large"
    assert db.get_prefs("Jeannie", "coffee")["size"] == "small"


def test_prefs_isolated_per_action(vault):
    db.save_prefs("John", "coffee", {"size": "large"})
    db.save_prefs("John", "grocery", {"store": "Costco"})
    assert "store" not in db.get_prefs("John", "coffee")
    assert db.get_prefs("John", "grocery")["store"] == "Costco"


def test_prefs_upsert_overwrites(vault):
    db.save_prefs("John", "coffee", {"size": "small"})
    db.save_prefs("John", "coffee", {"size": "large"})
    assert db.get_prefs("John", "coffee")["size"] == "large"


# ── audit log ─────────────────────────────────────────────────────────────────

def test_get_audit_log_all(vault):
    db.create_ticket("TKT-AL1", "Task 1", "work", "normal")
    db.create_ticket("TKT-AL2", "Task 2", "work", "normal")
    logs = db.get_audit_log()
    assert len(logs) >= 2


def test_get_audit_log_filtered_by_ticket(vault):
    db.create_ticket("TKT-AF1", "Task 1", "work", "normal")
    db.create_ticket("TKT-AF2", "Task 2", "work", "normal")
    logs = db.get_audit_log("TKT-AF1")
    assert all(l["ticket_id"] == "TKT-AF1" for l in logs)


# ── get_ticket ────────────────────────────────────────────────────────────────

def test_get_ticket_returns_dict(vault):
    db.create_ticket("TKT-GT1", "Get this", "work", "normal", 20)
    t = db.get_ticket("TKT-GT1")
    assert t is not None
    assert t["title"] == "Get this"
    assert t["domain"] == "work"


def test_get_ticket_none_for_missing(vault):
    assert db.get_ticket("TKT-DOES-NOT-EXIST") is None


def test_get_ticket_contains_status(vault):
    db.create_ticket("TKT-GT2", "Status check", "hobby", "high", 15)
    t = db.get_ticket("TKT-GT2")
    assert t["status"] == "queued"


# ── list_recent ───────────────────────────────────────────────────────────────

def test_list_recent_empty(vault):
    assert db.list_recent() == []


def test_list_recent_returns_all(vault):
    db.create_ticket("TKT-LR1", "First", "work", "normal")
    db.create_ticket("TKT-LR2", "Second", "hobby", "high")
    recent = db.list_recent()
    assert len(recent) == 2


def test_list_recent_ordered_newest_first(vault):
    import time
    db.create_ticket("TKT-LR3", "Older", "work", "normal")
    time.sleep(0.01)
    db.create_ticket("TKT-LR4", "Newer", "hobby", "normal")
    recent = db.list_recent()
    assert recent[0]["id"] == "TKT-LR4"


def test_list_recent_respects_limit(vault):
    for i in range(10):
        db.create_ticket(f"TKT-LR{i+10}", f"Task {i}", "work", "normal")
    assert len(db.list_recent(limit=5)) == 5


# ── backup_db ─────────────────────────────────────────────────────────────────

def test_backup_db_creates_file(vault, tmp_path):
    db.create_ticket("TKT-BK1", "Backup me", "work", "normal")
    dest = tmp_path / "backups" / "pensieve.db.bak"
    db.backup_db(dest)
    assert dest.exists()
    assert dest.stat().st_size > 0


def test_backup_db_contains_data(vault, tmp_path):
    import sqlite3
    db.create_ticket("TKT-BK2", "Preserved in backup", "property", "normal")
    dest = tmp_path / "pensieve.bak"
    db.backup_db(dest)
    with sqlite3.connect(str(dest)) as bk:
        row = bk.execute("SELECT title FROM tickets WHERE id='TKT-BK2'").fetchone()
    assert row is not None
    assert row[0] == "Preserved in backup"
