#!/usr/bin/env bash
# Deploy pensieve-sms to Arch Linux box.
set -e

REPO_DIR="$HOME/pensieve-sms"

echo "==> Cloning / pulling repo"
if [[ -d "$REPO_DIR/.git" ]]; then
  git -C "$REPO_DIR" pull
else
  git clone git@github.com:jbaycroft/pensieve-sms.git "$REPO_DIR"
fi

echo "==> Setting up virtualenv"
python3 -m venv "$REPO_DIR/.venv"
"$REPO_DIR/.venv/bin/pip" install --upgrade pip
"$REPO_DIR/.venv/bin/pip" install -r "$REPO_DIR/requirements.txt"

echo "==> Installing systemd unit"
sudo cp "$REPO_DIR/deploy/pensieve-flask.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pensieve-flask

echo "==> Done. Check status: systemctl status pensieve-flask"
