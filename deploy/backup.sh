#!/usr/bin/env bash
# deploy/backup.sh - online SQLite backup with 7-day rotation
# Safe to call while Flask is running.
# Called by: make backup / systemd pensieve-backup.timer

set -euo pipefail

ENV_FILE="/etc/pensieve.env"
VAULT_ROOT="$(sudo grep "^VAULT_ROOT=" "$ENV_FILE" 2>/dev/null | cut -d= -f2-)"

if [[ -z "$VAULT_ROOT" ]]; then
  echo "ERROR: Cannot read VAULT_ROOT from $ENV_FILE" >&2
  exit 1
fi

DB_SRC="${VAULT_ROOT}/.pensieve-app/pensieve.db"
BACKUP_DIR="${VAULT_ROOT}/.pensieve-app/backups"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
DEST="${BACKUP_DIR}/pensieve-${TIMESTAMP}.db"

if [[ ! -f "$DB_SRC" ]]; then
  echo "ERROR: Source DB not found: $DB_SRC" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

# Online backup - Python sqlite3 API
REPO_DIR="$HOME/pensieve-sms"
VENV_PYTHON="${REPO_DIR}/.venv/bin/python"

if [[ -x "$VENV_PYTHON" ]]; then
  "$VENV_PYTHON" -c "
 import sqlite3, pathlib
 src, dst = pathlib.Path('$DB_SRC'), pathlib.Path('$DEST')
 dst.parent.mkdir(parents=True, exist_ok=True)
 with sqlite3.connect(str(src)) as s, sqlite3.connect(str(dst)) as d:
     s.backup(d, pages=100)
 "
  echo "[backup] Backup written: $DEST"
else
  cp "$DB_SRC" "$DEST"
  echo "[backup] File copy backup: $DEST"
fi

# Rotate: keep 7 most recent
ls -1t "${BACKUP_DIR}/pensieve-"*.db 2>/dev/null | tail -n +8 | xargs -r rm -f
echo "[backup] Done. Remaining: $(ls "$BACKUP_DIR" | wc -l)"
