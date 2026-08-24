"""
vault.py - Pensieve vault writer. Cross-platform via pathlib.

Data model
----------
Primary store: SQLite database (app/database.py)
Display layer: Obsidian .md files (written as a side effect on every change)

The Obsidian vault is the *view*. The database is the *truth*.
Scripts and Obsidian scripts may still read .md files — they are kept in sync.

VAULT_ROOT env var:
  Windows dev:  c:\\vaults\\Pensieve
  Arch deploy:  /home/john/vault/Pensieve
"""

import os
import re
import datetime
import logging
import pathlib
from typing import Optional

log = logging.getLogger(__name__)
_VAULT_ROOT: Optional[pathlib.Path] = None

PRIORITY_MAP = {"urgent": "critical", "high": "high", "normal": "normal"}


def vault_root() -> pathlib.Path:
    global _VAULT_ROOT
    if _VAULT_ROOT is None:
        raw = os.environ.get("VAULT_ROOT")
        if not raw:
            raise RuntimeError("VAULT_ROOT environment variable is not set")
        _VAULT_ROOT = pathlib.Path(raw)
    return _VAULT_ROOT


# ── public API ────────────────────────────────────────────────────────────────

def write_ticket(title: str, domain: str, priority: str, est_min: int = 30) -> str:
    """
    Create a new ticket.

    1. Writes to SQLite (primary — source of truth)
    2. Writes .md file to vault (display layer for Obsidian)

    Returns ticket_id.
    """
    from . import database

    now = datetime.datetime.now()
    ticket_id = "TKT-" + now.strftime("%Y%m%d%H%M")

    # 1. Primary: SQLite
    database.create_ticket(ticket_id, title, domain, priority, est_min)

    # 2. Side effect: .md file for Obsidian
    _write_ticket_md(ticket_id, title, domain, priority, est_min, now)

    log.info("Wrote ticket %s", ticket_id)
    return ticket_id


def write_index(ticket_id: str, priority: str) -> None:
    """
    Insert ticket into the queue.

    1. Updates queue_order in SQLite (primary)
    2. Updates Index.md in vault (display layer for Obsidian)

    Priority rules:
      urgent → position 1 (new HEAD)
      high   → position 2 (after current HEAD)
      normal → tail (FIFO)
    """
    from . import database

    # 1. Primary: SQLite queue
    database.enqueue_ticket(ticket_id, priority)

    # 2. Side effect: update Index.md
    _update_index_md(ticket_id, priority)

    log.info("Queued %s (%s)", ticket_id, priority)


def close_ticket(ticket_id: str, actor: str = "system") -> None:
    """
    Mark a ticket done.

    1. Updates SQLite status + removes from queue_order
    2. Updates .md file status field and Index.md
    """
    from . import database

    # 1. Primary: SQLite
    database.close_ticket(ticket_id, actor=actor)

    # 2. Side effect: update ticket .md
    _close_ticket_md(ticket_id)

    # 3. Side effect: remove pointer from Index.md
    _remove_from_index_md(ticket_id)

    log.info("Closed ticket %s (actor=%s)", ticket_id, actor)


# ── markdown side effects ─────────────────────────────────────────────────────

def _write_ticket_md(
    ticket_id: str,
    title: str,
    domain: str,
    priority: str,
    est_min: int,
    now: datetime.datetime,
) -> None:
    """Write the Obsidian-facing .md file for a new ticket."""
    date_str = now.strftime("%Y-%m-%d")
    prio_display = PRIORITY_MAP.get(priority, "normal")

    ticket_dir = vault_root() / "00_Queue" / "Tickets"
    ticket_dir.mkdir(parents=True, exist_ok=True)

    body = "\n".join([
        "---",
        f"id: {ticket_id}",
        f"title: {title}",
        f"domain: {domain}",
        f"priority: {prio_display}",
        "status: queued",
        f"created: {date_str}",
        "energy: medium",
        f"est_min: {est_min}",
        "recur: false",
        "source: sms",
        f"tags: [{domain}, sms]",
        "---",
        "",
        title,
        "",
    ])

    (ticket_dir / f"{ticket_id}.md").write_text(body, encoding="utf-8")


def _update_index_md(ticket_id: str, priority: str) -> None:
    """Insert [[ticket_id]] into Index.md using the same priority insertion rules."""
    index_path = vault_root() / "00_Queue" / "Index.md"
    if not index_path.exists():
        raise FileNotFoundError(f"Index.md not found at {index_path}")

    content = index_path.read_text(encoding="utf-8")
    pointer = f"[[{ticket_id}]]\n"

    if priority == "urgent":
        m = re.search(r"%%[\s\S]*?%%\n?", content)
        pos = m.end() if m else 0
        content = content[:pos] + "\n" + pointer + content[pos:]
    elif priority == "high":
        m = re.search(r"\[\[.*?\]\]\n", content)
        pos = m.end() if m else len(content)
        content = content[:pos] + pointer + content[pos:]
    else:
        if not content.endswith("\n"):
            content += "\n"
        content += pointer

    index_path.write_text(content, encoding="utf-8")


def _close_ticket_md(ticket_id: str) -> None:
    """Update status: queued → done in the ticket's .md file."""
    today = datetime.date.today().isoformat()
    ticket_path = vault_root() / "00_Queue" / "Tickets" / f"{ticket_id}.md"
    if not ticket_path.exists():
        return
    text = ticket_path.read_text(encoding="utf-8")
    text = re.sub(r"^status: \S+$", "status: done", text, flags=re.MULTILINE)
    if "completed:" not in text:
        text = re.sub(
            r"^status: done$",
            f"status: done\ncompleted: {today}",
            text,
            flags=re.MULTILINE,
        )
    ticket_path.write_text(text, encoding="utf-8")


def _remove_from_index_md(ticket_id: str) -> None:
    """Remove [[ticket_id]] pointer from Index.md."""
    index_path = vault_root() / "00_Queue" / "Index.md"
    if not index_path.exists():
        return
    content = index_path.read_text(encoding="utf-8")
    content = content.replace(f"[[{ticket_id}]]\n", "")
    content = content.replace(f"[[{ticket_id}]]", "")
    index_path.write_text(content, encoding="utf-8")

