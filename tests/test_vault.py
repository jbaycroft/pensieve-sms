import pytest
import app.vault as vault_mod


@pytest.fixture(autouse=True)
def reset_vault_root():
    vault_mod._VAULT_ROOT = None
    yield
    vault_mod._VAULT_ROOT = None


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
    return tmp_path


def test_write_ticket_creates_file(fake_vault):
    tid = vault_mod.write_ticket("Buy CO2 sensor", "hydroponics", "normal", 30)
    assert tid.startswith("TKT-")
    path = fake_vault / "00_Queue" / "Tickets" / f"{tid}.md"
    assert path.exists()
    content = path.read_text()
    assert "source: sms" in content
    assert "domain: hydroponics" in content
    assert "est_min: 30" in content
    assert "priority: normal" in content


def test_write_ticket_urgent_priority(fake_vault):
    tid = vault_mod.write_ticket("Fix prod", "work", "urgent", 15)
    path = fake_vault / "00_Queue" / "Tickets" / f"{tid}.md"
    assert "priority: critical" in path.read_text()


def test_write_index_normal_appends(fake_vault):
    tid = vault_mod.write_ticket("task", "work", "normal")
    vault_mod.write_index(tid, "normal")
    lines = [
        l for l in (fake_vault / "00_Queue" / "Index.md").read_text().splitlines()
        if l.startswith("[[")
    ]
    assert lines[-1] == f"[[{tid}]]"


def test_write_index_urgent_at_head(fake_vault):
    tid = vault_mod.write_ticket("urgent task", "work", "urgent")
    vault_mod.write_index(tid, "urgent")
    lines = [
        l for l in (fake_vault / "00_Queue" / "Index.md").read_text().splitlines()
        if l.startswith("[[")
    ]
    assert lines[0] == f"[[{tid}]]"


def test_write_index_high_at_position_2(fake_vault):
    tid = vault_mod.write_ticket("high task", "work", "high")
    vault_mod.write_index(tid, "high")
    lines = [
        l for l in (fake_vault / "00_Queue" / "Index.md").read_text().splitlines()
        if l.startswith("[[")
    ]
    # Should be second: existing ticket is first, new high-priority is second
    assert lines[0] == "[[TKT-EXISTING]]"
    assert lines[1] == f"[[{tid}]]"
