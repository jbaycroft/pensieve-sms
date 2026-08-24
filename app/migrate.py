"""
app/migrate.py — One-time import of existing .md tickets into SQLite.

Run once after upgrading to the SQLite-backed data model:

    cd ~/pensieve-sms
    VAULT_ROOT=/path/to/Pensieve .venv/bin/python -m app.migrate

Reads:
  - 00_Queue/Index.md  → queue order
  - 00_Queue/Tickets/  → ticket frontmatter

Writes:
  - SQLite: tickets + queue_order tables

Safe to re-run (INSERT OR IGNORE — already-migrated tickets are skipped).
"""
import os
import re
import sys
import json
import logging
import pathlib
import datetime

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)


def _parse_frontmatter(text: str) -> dict:
    m = re.match(r"^---\n([\s\S]*?)\n---", text)
    if not m:
        return {}
    meta = {}
    for line in m.group(1).splitlines():
        if ": " in line:
            k, v = line.split(": ", 1)
            meta[k.strip()] = v.strip()
    return meta


def _queue_links_from_index(index_path: pathlib.Path) -> list[str]:
    """Return ordered list of ticket IDs from Index.md wikilinks."""
    if not index_path.exists():
        return []
    content = index_path.read_text(encoding="utf-8")
    body = re.sub(r"^---[\s\S]*?---\n?", "", content)
    body = re.sub(r"%%[\s\S]*?%%\n?", "", body)
    return re.findall(r"\[\[([^\]]+)\]\]", body)


def migrate() -> None:
    vault_root_str = os.environ.get("VAULT_ROOT")
    if not vault_root_str:
        log.error("VAULT_ROOT is not set")
        sys.exit(1)

    vault = pathlib.Path(vault_root_str)

    from app import database
    database.init_db()
    conn = database.get_conn()

    ticket_dir = vault / "00_Queue" / "Tickets"
    index_path  = vault / "00_Queue" / "Index.md"

    if not ticket_dir.exists():
        log.error("Tickets directory not found: %s", ticket_dir)
        sys.exit(1)

    # ── Step 1: import all ticket .md files ───────────────────────────────────
    md_files = sorted(ticket_dir.glob("TKT-*.md"))
    log.info("Found %d .md ticket files", len(md_files))

    imported = 0
    skipped  = 0
    for fp in md_files:
        ticket_id = fp.stem
        meta = _parse_frontmatter(fp.read_text(encoding="utf-8"))

        title    = meta.get("title", ticket_id)
        domain   = meta.get("domain", "general")
        priority = meta.get("priority", "normal")
        status   = meta.get("status", "queued")
        est_min  = int(meta.get("est_min", "30"))
        created  = meta.get("created", datetime.date.today().isoformat())
        tags_raw = meta.get("tags", "")
        tags     = json.dumps([t.strip() for t in tags_raw.strip("[]").split(",") if t.strip()])

        # Map display priority back to internal value
        prio_map = {"critical": "urgent", "high": "high", "normal": "normal"}
        priority = prio_map.get(priority, priority)

        existing = conn.execute(
            "SELECT id FROM tickets WHERE id=?", (ticket_id,)
        ).fetchone()
        if existing:
            log.debug("  skip  %s (already in DB)", ticket_id)
            skipped += 1
            continue

        conn.execute(
            """INSERT INTO tickets
                   (id, title, domain, priority, status, source, est_min, tags, created_at)
               VALUES (?, ?, ?, ?, ?, 'sms', ?, ?, ?)""",
            (ticket_id, title, domain, priority, status, est_min, tags,
             f"{created}T00:00:00"),
        )
        log.info("  import %s  %s", ticket_id, title[:60])
        imported += 1

    conn.commit()
    log.info("Tickets: %d imported, %d skipped", imported, skipped)

    # ── Step 2: rebuild queue_order from Index.md ─────────────────────────────
    queued_links = _queue_links_from_index(index_path)
    log.info("Index.md has %d queued ticket links", len(queued_links))

    position = 0
    for tid in queued_links:
        row = conn.execute(
            "SELECT status FROM tickets WHERE id=?", (tid,)
        ).fetchone()
        if not row:
            log.warning("  skip  %s (not in tickets table — orphaned link)", tid)
            continue
        if row["status"] != "queued":
            log.debug("  skip  %s (status=%s)", tid, row["status"])
            continue

        # Skip if already in queue_order
        if conn.execute(
            "SELECT 1 FROM queue_order WHERE ticket_id=?", (tid,)
        ).fetchone():
            log.debug("  skip  %s (already in queue_order)", tid)
            continue

        position += 1
        conn.execute(
            "INSERT INTO queue_order (position, ticket_id) VALUES (?, ?)",
            (position, tid),
        )
        log.info("  queue pos=%d  %s", position, tid)

    conn.commit()
    log.info("Queue rebuilt: %d tickets", position)
    log.info("Migration complete.")


if __name__ == "__main__":
    migrate()
