"""
vault.py - Pensieve vault writer. Cross-platform via pathlib.

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


def write_ticket(title: str, domain: str, priority: str, est_min: int = 30) -> str:
    """Create ticket file. Returns ticket ID."""
    now       = datetime.datetime.now()
    ticket_id = "TKT-" + now.strftime("%Y%m%d%H%M")
    date_str  = now.strftime("%Y-%m-%d")
    prio      = PRIORITY_MAP.get(priority, "normal")

    ticket_dir = vault_root() / "00_Queue" / "Tickets"
    ticket_dir.mkdir(parents=True, exist_ok=True)

    body = "\n".join([
        "---",
        f"id: {ticket_id}",
        f"title: {title}",
        f"domain: {domain}",
        f"priority: {prio}",
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

    ticket_path = ticket_dir / f"{ticket_id}.md"
    ticket_path.write_text(body, encoding="utf-8")
    log.info("Wrote ticket %s", ticket_id)
    return ticket_id


def write_index(ticket_id: str, priority: str) -> None:
    """
    Insert [[ticket_id]] pointer into Index.md.
      urgent -> prepend after %% comment block (becomes HEAD)
      high   -> insert after first existing link (position 2)
      normal -> append to FIFO tail
    """
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
    log.info("Updated Index.md - %s (%s)", ticket_id, priority)
