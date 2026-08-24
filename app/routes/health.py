"""
routes/health.py — /health and /health/db endpoints.

GET /health      → overall status JSON (used by monitoring, systemd ExecStartPost)
GET /health/db   → detailed DB stats (WAL info, row counts per table)

HTTP 200 = healthy, 503 = degraded (still responds, but something is wrong).
"""

import time
import os
import sqlite3
import logging
from flask import Blueprint, jsonify, Response

from ..database import get_conn, get_queue

log = logging.getLogger(__name__)
health_bp = Blueprint("health", __name__)

_START_TIME = time.monotonic()
VERSION = "1.0.0"


def _db_ok() -> tuple[bool, str]:
    """Quick DB liveness check. Returns (ok, message)."""
    try:
        conn = get_conn()
        row = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()
        _ = row[0]
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


def _vault_ok() -> bool:
    """Check VAULT_ROOT exists and Index.md is present."""
    vault = os.environ.get("VAULT_ROOT", "")
    if not vault:
        return False
    import pathlib
    idx = pathlib.Path(vault) / "00_Queue" / "Index.md"
    return idx.exists()


@health_bp.route("/health")
def health() -> Response:
    db_healthy, db_msg = _db_ok()
    vault_healthy = _vault_ok()
    uptime = round(time.monotonic() - _START_TIME, 1)

    try:
        queue_depth = len(get_queue(limit=200))
    except Exception:
        queue_depth = -1

    status = "ok" if (db_healthy and vault_healthy) else "degraded"
    payload = {
        "status": status,
        "version": VERSION,
        "uptime_s": uptime,
        "db_ok": db_healthy,
        "db_message": db_msg,
        "vault_ok": vault_healthy,
        "queue_depth": queue_depth,
    }
    http_code = 200 if status == "ok" else 503
    return jsonify(payload), http_code


@health_bp.route("/health/db")
def health_db() -> Response:
    """Detailed DB introspection for debugging."""
    try:
        conn = get_conn()
        tables = {}
        for (tbl,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall():
            count = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]  # noqa: S608
            tables[tbl] = count

        wal_row = conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
        wal = {
            "busy": wal_row[0],
            "log": wal_row[1],
            "checkpointed": wal_row[2],
        } if wal_row else {}

        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        return jsonify({
            "tables": tables,
            "wal_checkpoint": wal,
            "integrity": integrity[0] if integrity else "unknown",
        })
    except Exception as exc:
        log.exception("health_db failed")
        return jsonify({"error": str(exc)}), 503