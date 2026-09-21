#!/usr/bin/env bash
# pensieve-sync.sh — Auto-sync pensieve-sms repo with GitHub.
# Runs as jbaycroft via systemd timer. Logs to journal.
#
# Behaviour:
#   1. git add -A + commit (no-op if working tree is clean)
#   2. git pull --rebase origin master
#   3. git push origin master
#   4. If any tracked files changed, restart pensieve-flask
#
# Exit codes:
#   0 — success (sync done or nothing to sync)
#   1 — git operation failed

set -euo pipefail

REPO="/home/jbaycroft/TheBurrow/pensieve-sms"
BRANCH="master"
REMOTE="origin"
SERVICE="pensieve-flask.service"

cd "$REPO"

# ── snapshot before pull ─────────────────────────────────────────────────────
HEAD_BEFORE=$(git rev-parse HEAD)

# ── commit local changes (if any) ───────────────────────────────────────────
if ! git diff --quiet HEAD 2>/dev/null || [ -n "$(git ls-files --others --exclude-standard)" ]; then
    git add -A
    git commit -m "auto-sync $(date '+%Y-%m-%d %H:%M')" --no-verify
    echo "[sync] Committed local changes"
else
    echo "[sync] Working tree clean — nothing to commit"
fi

# ── pull remote changes ─────────────────────────────────────────────────────
git pull --rebase "$REMOTE" "$BRANCH" 2>&1 || {
    echo "[sync] Pull failed — aborting rebase if in progress"
    git rebase --abort 2>/dev/null || true
    exit 1
}

# ── push ─────────────────────────────────────────────────────────────────────
git push "$REMOTE" "$BRANCH" 2>&1 || {
    echo "[sync] Push failed"
    exit 1
}

# ── restart flask if code changed ────────────────────────────────────────────
HEAD_AFTER=$(git rev-parse HEAD)
if [ "$HEAD_BEFORE" != "$HEAD_AFTER" ]; then
    echo "[sync] Code changed ($HEAD_BEFORE → $HEAD_AFTER) — restarting $SERVICE"
    sudo systemctl restart "$SERVICE"
else
    echo "[sync] No changes from remote — no restart needed"
fi

echo "[sync] Done"
