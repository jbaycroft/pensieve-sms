"""
app/database.py — SQLite primary data store.

WAL mode + thread-local connections. No external deps — sqlite3 is Python stdlib.
DB file: VAULT_ROOT/.pensieve-app/pensieve.db

Public API
----------
init_db()                                   create schema, safe to call repeatedly
get_conn() -> Connection                    thread-local connection
close_conn()                                close thread-local connection (test teardown)

create_ticket(id, title, domain, priority, est_min, source, tags)
enqueue_ticket(ticket_id, priority)         insert into queue at priority position
get_queue(limit) -> list[dict]              ordered queue
close_ticket(ticket_id, actor)              mark done, remove from queue
get_audit_log(ticket_id, limit) -> list

get_prefs(user, action) -> dict
save_prefs(user, action, prefs)
"""

import json
import sqlite3
import logging
import datetime
import threading
import pathlib
from typing import Optional

log = logging.getLogger(__name__)

_local = threading.local()
_DB_PATH: Optional[pathlib.Path] = None

# ── schema ────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    domain       TEXT DEFAULT 'general',
    priority     TEXT DEFAULT 'normal',
    status       TEXT DEFAULT 'queued',
    source       TEXT DEFAULT 'sms',
    est_min      INTEGER DEFAULT 30,
    energy       TEXT DEFAULT 'medium',
    recur        INTEGER DEFAULT 0,
    tags         TEXT DEFAULT '[]',
    body         TEXT DEFAULT '',
    created_at   TEXT NOT NULL,
    completed_at TEXT,
    embedding_id TEXT
);

CREATE TABLE IF NOT EXISTS queue_order (
    position  INTEGER NOT NULL,
    ticket_id TEXT NOT NULL UNIQUE REFERENCES tickets(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_queue_pos ON queue_order(position);

CREATE TABLE IF NOT EXISTS preferences (
    user       TEXT NOT NULL,
    action     TEXT NOT NULL,
    data_json  TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user, action)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    actor       TEXT NOT NULL DEFAULT 'system',
    action      TEXT NOT NULL,
    ticket_id   TEXT,
    detail_json TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_audit_ticket ON audit_log(ticket_id);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts);

CREATE TABLE IF NOT EXISTS people (
    name            TEXT PRIMARY KEY,
    phone           TEXT,
    email           TEXT,
    context_json    TEXT DEFAULT '{}',
    last_contact_at TEXT
);
"""


# ── connection management ─────────────────────────────────────────────────────

def _db_path() -> pathlib.Path:
    global _DB_PATH
    if _DB_PATH is None:
        from .vault import vault_root
        _DB_PATH = vault_root() / ".pensieve-app" / "pensieve.db"
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return _DB_PATH


def get_conn() -> sqlite3.Connection:
    """Return thread-local WAL connection. Creates it on first call per thread."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        path = _db_path()
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")   # wait up to 5s if DB locked
        _local.conn = conn
        log.debug("Opened DB connection: %s", path)
    return conn


def close_conn() -> None:
    """Close thread-local connection. Call in test teardown or thread shutdown."""
    conn = getattr(_local, "conn", None)
    if conn:
        try:
            conn.close()
        except Exception:
            pass
        _local.conn = None


def init_db() -> None:
    """Create schema if not exists. Idempotent — safe to call on every startup."""
    conn = get_conn()
    conn.executescript(_SCHEMA)
    conn.commit()
    log.info("DB ready: %s", _db_path())


# ── tickets ───────────────────────────────────────────────────────────────────

def create_ticket(
    id: str,
    title: str,
    domain: str,
    priority: str,
    est_min: int = 30,
    source: str = "sms",
    tags: list = None,
) -> None:
    """Insert ticket record only. Call enqueue_ticket() separately for queue position."""
    now = datetime.datetime.now().isoformat()
    tags_json = json.dumps(tags or [domain])
    conn = get_conn()
    conn.execute(
        """INSERT OR IGNORE INTO tickets
               (id, title, domain, priority, status, source, est_min, tags, created_at)
           VALUES (?, ?, ?, ?, 'queued', ?, ?, ?, ?)""",
        (id, title, domain, priority, source, est_min, tags_json, now),
    )
    _audit(conn, "create_ticket", ticket_id=id,
           detail={"title": title, "domain": domain, "priority": priority})
    conn.commit()


def enqueue_ticket(ticket_id: str, priority: str) -> None:
    """
    Insert ticket_id into queue_order at priority-appropriate position.

    urgent → position 1 (new HEAD, all others shift down)
    high   → position 2 (after current HEAD, positions ≥ 2 shift down)
    normal → MAX(position) + 1 (tail)
    """
    conn = get_conn()
    if priority == "urgent":
        conn.execute("UPDATE queue_order SET position = position + 1")
        conn.execute(
            "INSERT OR IGNORE INTO queue_order (position, ticket_id) VALUES (1, ?)",
            (ticket_id,),
        )
    elif priority == "high":
        conn.execute(
            "UPDATE queue_order SET position = position + 1 WHERE position >= 2"
        )
        conn.execute(
            "INSERT OR IGNORE INTO queue_order (position, ticket_id) VALUES (2, ?)",
            (ticket_id,),
        )
    else:
        conn.execute(
            """INSERT OR IGNORE INTO queue_order (position, ticket_id)
               SELECT COALESCE(MAX(position), 0) + 1, ? FROM queue_order""",
            (ticket_id,),
        )
    conn.commit()


def get_queue(limit: int = 20) -> list[dict]:
    """Return ordered queue as list of dicts (id, title, domain, priority, est_min, status)."""
    rows = get_conn().execute(
        """SELECT t.id, t.title, t.domain, t.priority, t.est_min, t.status
           FROM queue_order q
           JOIN tickets t ON t.id = q.ticket_id
           WHERE t.status IN ('queued', 'active')
           ORDER BY q.position
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def close_ticket(ticket_id: str, actor: str = "system") -> None:
    """Mark ticket done, remove from queue, compact positions."""
    now = datetime.datetime.now().isoformat()
    conn = get_conn()
    conn.execute(
        "UPDATE tickets SET status='done', completed_at=? WHERE id=?",
        (now, ticket_id),
    )
    conn.execute("DELETE FROM queue_order WHERE ticket_id=?", (ticket_id,))
    _compact_queue(conn)
    _audit(conn, "close_ticket", ticket_id=ticket_id, detail={"actor": actor})
    conn.commit()


def _compact_queue(conn: sqlite3.Connection) -> None:
    """Renumber queue positions 1..N after a removal."""
    rows = conn.execute(
        "SELECT ticket_id FROM queue_order ORDER BY position"
    ).fetchall()
    for i, row in enumerate(rows, 1):
        conn.execute(
            "UPDATE queue_order SET position=? WHERE ticket_id=?", (i, row[0])
        )


# ── preferences ───────────────────────────────────────────────────────────────

def get_prefs(user: str, action: str) -> dict:
    row = get_conn().execute(
        "SELECT data_json FROM preferences WHERE user=? AND action=?",
        (user, action),
    ).fetchone()
    if row:
        try:
            return json.loads(row[0])
        except Exception:
            return {}
    return {}


def save_prefs(user: str, action: str, prefs: dict) -> None:
    now = datetime.datetime.now().isoformat()
    conn = get_conn()
    conn.execute(
        """INSERT INTO preferences (user, action, data_json, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(user, action) DO UPDATE SET
               data_json  = excluded.data_json,
               updated_at = excluded.updated_at""",
        (user, action, json.dumps(prefs), now),
    )
    conn.commit()


# ── audit log ─────────────────────────────────────────────────────────────────

def _audit(
    conn: sqlite3.Connection,
    action: str,
    ticket_id: str = None,
    actor: str = "system",
    detail: dict = None,
) -> None:
    """Insert an audit log row. Call inside an open transaction (caller commits)."""
    conn.execute(
        """INSERT INTO audit_log (ts, actor, action, ticket_id, detail_json)
           VALUES (?, ?, ?, ?, ?)""",
        (
            datetime.datetime.now().isoformat(),
            actor,
            action,
            ticket_id,
            json.dumps(detail or {}),
        ),
    )


def get_audit_log(ticket_id: str = None, limit: int = 50) -> list[dict]:
    conn = get_conn()
    if ticket_id:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE ticket_id=? ORDER BY ts DESC LIMIT ?",
            (ticket_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
