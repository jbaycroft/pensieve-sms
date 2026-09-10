import pytest
import app.vault as vault_mod
import app.database as db_mod


@pytest.fixture(autouse=True)
def reset_vault_root():
    vault_mod._VAULT_ROOT = None
    db_mod._DB_PATH = None
    db_mod.close_conn()
    yield
    vault_mod._VAULT_ROOT = None
    db_mod._DB_PATH = None
    db_mod.close_conn()


@pytest.fixture
def fake_vault(tmp_path, monkeypatch):
    tickets = tmp_path / "00_Queue" / "Tickets"
    tickets.mkdir(parents=True)
    index = tmp_path / "00_Queue" / "Index.md"
    index.write_text(
        "---\ntest: true\n---\n%%\nFIFO\n%%\n\n[[TKT-EXISTING]]\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
    # Seed DB so queue ordering tests work with pre-existing ticket
    db_mod.init_db()
    db_mod.create_ticket("TKT-EXISTING", "Existing task", "work", "month")
    db_mod.enqueue_ticket("TKT-EXISTING", "month")
    return tmp_path


def test_write_ticket_creates_file(fake_vault):
    tid = vault_mod.write_ticket("Buy CO2 sensor", "hydroponics", "month", 30)
    assert tid.startswith("TKT-")
    path = fake_vault / "00_Queue" / "Tickets" / f"{tid}.md"
    assert path.exists()
    content = path.read_text()
    assert "source: sms" in content
    assert "domain: hydroponics" in content
    assert "est_min: 30" in content
    assert "priority: month" in content


def test_write_ticket_day_priority(fake_vault):
    tid = vault_mod.write_ticket("Fix prod", "work", "day", 15)
    path = fake_vault / "00_Queue" / "Tickets" / f"{tid}.md"
    assert "priority: day" in path.read_text()


def test_write_index_normal_appends(fake_vault):
    tid = vault_mod.write_ticket("task", "work", "month")
    vault_mod.write_index(tid, "month")
    lines = [
        l for l in (fake_vault / "00_Queue" / "Index.md").read_text().splitlines()
        if l.startswith("[[")
    ]
    assert lines[-1] == f"[[{tid}]]"


def test_write_index_day_at_head(fake_vault):
    tid = vault_mod.write_ticket("day task", "work", "day")
    vault_mod.write_index(tid, "day")
    lines = [
        l for l in (fake_vault / "00_Queue" / "Index.md").read_text().splitlines()
        if l.startswith("[[")
    ]
    assert lines[0] == f"[[{tid}]]"


def test_write_index_week_at_position_2(fake_vault):
    tid = vault_mod.write_ticket("week task", "work", "week")
    vault_mod.write_index(tid, "week")
    lines = [
        l for l in (fake_vault / "00_Queue" / "Index.md").read_text().splitlines()
        if l.startswith("[[")
    ]
    # Should be second: existing ticket is first, new high-priority is second
    assert lines[0] == "[[TKT-EXISTING]]"
    assert lines[1] == f"[[{tid}]]"
