#!/usr/bin/env bash
# pensieve-sms — guided installer for Arch Linux
# Run once on the Arch box. Everything is handled for you.
set -e

# ── colours ───────────────────────────────────────────────────────────────────
GRN='\033[0;32m'; YLW='\033[1;33m'; BLU='\033[0;34m'; RED='\033[0;31m'; NC='\033[0m'
hdr()  { echo -e "\n${BLU}══>${NC} $1"; }
ok()   { echo -e "  ${GRN}✓${NC} $1"; }
warn() { echo -e "  ${YLW}!${NC} $1"; }
die()  { echo -e "  ${RED}✗${NC} $1"; exit 1; }

ask() {
  # ask <VAR_NAME> <human description> [example]
  local var="$1" desc="$2" ex="$3"
  echo -e "\n  ${YLW}${desc}${NC}"
  [[ -n "$ex" ]] && echo -e "  Example: ${ex}"
  read -r -p "  ▶ " val
  [[ -z "$val" ]] && die "Value required for ${var}"
  printf '%s=%s\n' "$var" "$val"
}

REPO_DIR="$HOME/pensieve-sms"
ENV_FILE="/etc/pensieve.env"
SVC_URL_FILE="/var/log/pensieve-tunnel-url.txt"

echo ""
echo -e "${BLU}╔══════════════════════════════════════════╗${NC}"
echo -e "${BLU}║       pensieve-sms  —  installer         ║${NC}"
echo -e "${BLU}╚══════════════════════════════════════════╝${NC}"
echo ""
echo "  This script will:"
echo "    1. Clone the pensieve-sms repo"
echo "    2. Install Python dependencies"
echo "    3. Collect your credentials (written to ${ENV_FILE})"
echo "    4. Start the Flask service"
echo "    5. Start a Cloudflare Tunnel"
echo "    6. Print the exact URL to paste into Twilio"
echo ""
read -r -p "  Press Enter to begin…"

# ── 1. repo ───────────────────────────────────────────────────────────────────
hdr "Step 1/6 — Repo"
if [[ -d "$REPO_DIR/.git" ]]; then
  git -C "$REPO_DIR" pull --ff-only
  ok "Repo updated"
else
  git clone git@github.com:jbaycroft/pensieve-sms.git "$REPO_DIR"
  ok "Repo cloned to $REPO_DIR"
fi

# ── 2. python deps ────────────────────────────────────────────────────────────
hdr "Step 2/6 — Python dependencies"
python3 -m venv "$REPO_DIR/.venv"
"$REPO_DIR/.venv/bin/pip" install --upgrade pip -q
"$REPO_DIR/.venv/bin/pip" install -r "$REPO_DIR/requirements.txt" -q
ok "Dependencies installed"

# ── 3. credentials ────────────────────────────────────────────────────────────
hdr "Step 3/6 — Credentials"
echo "  All values are written to ${ENV_FILE} (mode 600)."
echo "  Phone numbers must be E.164 format: +15551234567"
echo "  Twilio credentials are at: console.twilio.com → Account Info"
echo "  Gemini API key: aistudio.google.com/apikey"
echo ""

ENV=""
ENV+=$(ask TWILIO_ACCOUNT_SID  "Twilio Account SID"             "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")$'\n'
ENV+=$(ask TWILIO_AUTH_TOKEN    "Twilio Auth Token"              "(from Twilio Console → Account Info)")$'\n'
ENV+=$(ask TWILIO_FROM_NUMBER   "Your Twilio phone number"       "+12035550100")$'\n'
ENV+=$(ask SMS_ALLOWLIST        "Your personal cell (E.164)"     "+12035551234")$'\n'
ENV+=$(ask JEANNIE_NUMBER       "Jeannie's cell (E.164)"         "+12035559876")$'\n'
ENV+=$(ask GEMINI_API_KEY       "Gemini API key"                 "AIzaSy...")$'\n'
ENV+=$(ask VAULT_ROOT           "Full path to Pensieve vault on this machine" "$HOME/vault/Pensieve")$'\n'
ENV+="ENHANCE_MOCK=0"$'\n'
ENV+="TEST_ENDPOINT_ENABLED=0"$'\n'

printf '%s' "$ENV" | sudo tee "$ENV_FILE" > /dev/null
sudo chmod 600 "$ENV_FILE"
ok "Credentials written to $ENV_FILE (readable only by root)"

# ── 4. flask service ──────────────────────────────────────────────────────────
hdr "Step 4/6 — Flask service"
sudo cp "$REPO_DIR/deploy/pensieve-flask.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable pensieve-flask
sudo systemctl restart pensieve-flask
sleep 2
systemctl is-active --quiet pensieve-flask \
  && ok "Flask service running on 127.0.0.1:5005" \
  || die "Flask failed to start — run: journalctl -u pensieve-flask"

# ── 5. cloudflared ────────────────────────────────────────────────────────────
hdr "Step 5/6 — Cloudflare Tunnel"
if ! command -v cloudflared &>/dev/null; then
  echo "  Installing cloudflared…"
  if command -v yay &>/dev/null; then
    yay -S --noconfirm cloudflared
  elif command -v paru &>/dev/null; then
    paru -S --noconfirm cloudflared
  else
    CFVER=$(curl -s https://api.github.com/repos/cloudflare/cloudflared/releases/latest \
      | grep tag_name | cut -d'"' -f4)
    curl -sL "https://github.com/cloudflare/cloudflared/releases/download/${CFVER}/cloudflared-linux-amd64" \
      -o /tmp/cloudflared
    sudo install -m 755 /tmp/cloudflared /usr/local/bin/cloudflared
  fi
fi
ok "cloudflared $(cloudflared --version | head -1)"

# ── Cloudflare login ──────────────────────────────────────────────────────────
echo ""
echo "  Logging in to Cloudflare (free account required)."
echo "  A URL will be printed below — open it in a browser to authenticate."
echo "  If a browser opens automatically, complete the login there."
echo ""
cloudflared tunnel login
ok "Cloudflare login complete"

# ── Named tunnel or quick tunnel? ─────────────────────────────────────────────
echo ""
echo -e "  ${YLW}Do you have a domain managed by Cloudflare?${NC}"
echo "  (e.g. yourdomain.com registered at Cloudflare or using Cloudflare nameservers)"
echo "  A named tunnel gives you a permanent, human-readable webhook URL."
echo "  If you don't have one yet, get one at: cloudflare.com/products/registrar"
echo "  (cheapest option: ~\$10/yr for a .com, no markup)"
echo ""
read -r -p "  Do you have a Cloudflare-managed domain? [y/N] " HAS_DOMAIN

TUNNEL_NAME="pensieve"
TUNNEL_URL=""

if [[ "${HAS_DOMAIN,,}" == "y" ]]; then
  echo ""
  echo -e "  ${YLW}Enter the hostname for the Twilio webhook${NC}"
  echo "  Example: webhook.yourdomain.com  or  sms.yourdomain.com"
  read -r -p "  ▶ " WEBHOOK_HOST
  [[ -z "$WEBHOOK_HOST" ]] && die "Hostname required"

  # Create tunnel (ok if already exists)
  cloudflared tunnel create "$TUNNEL_NAME" 2>/dev/null || true

  TUNNEL_ID=$(cloudflared tunnel list --output json \
    | python3 -c "
import sys, json
tunnels = json.load(sys.stdin)
match = [t for t in tunnels if t['name'] == '${TUNNEL_NAME}']
print(match[0]['id'] if match else '')
" 2>/dev/null)
  [[ -z "$TUNNEL_ID" ]] && die "Could not find tunnel ID"

  # Write cloudflared config
  mkdir -p "$HOME/.cloudflared"
  cat > "$HOME/.cloudflared/config.yml" <<EOF
tunnel: ${TUNNEL_ID}
credentials-file: ${HOME}/.cloudflared/${TUNNEL_ID}.json

ingress:
  - hostname: ${WEBHOOK_HOST}
    service: http://127.0.0.1:5005
  - service: http_status:404
EOF

  # Route DNS
  cloudflared tunnel route dns "$TUNNEL_NAME" "$WEBHOOK_HOST"

  # Install as systemd service
  sudo tee /etc/systemd/system/pensieve-tunnel.service > /dev/null <<UNIT
[Unit]
Description=Pensieve Cloudflare Named Tunnel
After=network.target pensieve-flask.service
Requires=pensieve-flask.service

[Service]
Type=simple
User=${USER}
ExecStart=/usr/bin/cloudflared tunnel --config ${HOME}/.cloudflared/config.yml run ${TUNNEL_NAME}
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT

  sudo systemctl daemon-reload
  sudo systemctl enable pensieve-tunnel
  sudo systemctl restart pensieve-tunnel
  sleep 3

  TUNNEL_URL="https://${WEBHOOK_HOST}"
  ok "Named tunnel active → ${TUNNEL_URL}"
  echo ""
  warn "This URL is permanent. It will not change on reboot."

else
  # ── Quick tunnel fallback ─────────────────────────────────────────────────
  warn "No domain — using quick tunnel (trycloudflare.com)."
  warn "URL will change if this machine reboots. Update Twilio when that happens."
  warn "To get a permanent URL later: register a domain at cloudflare.com/products/registrar"
  warn "then re-run this script."

  sudo tee /etc/systemd/system/pensieve-tunnel.service > /dev/null <<UNIT
[Unit]
Description=Pensieve Cloudflare Quick Tunnel
After=network.target pensieve-flask.service
Requires=pensieve-flask.service

[Service]
Type=simple
User=${USER}
ExecStart=/usr/bin/cloudflared tunnel --url http://127.0.0.1:5005 \
    --no-autoupdate \
    --logfile /var/log/cloudflared-pensieve.log \
    --loglevel info
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT

  sudo systemctl daemon-reload
  sudo systemctl enable pensieve-tunnel
  sudo systemctl restart pensieve-tunnel

  echo "  Waiting for tunnel URL…"
  for i in $(seq 1 30); do
    TUNNEL_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' \
      /var/log/cloudflared-pensieve.log 2>/dev/null | tail -1)
    [[ -n "$TUNNEL_URL" ]] && break
    sleep 1
  done
  [[ -z "$TUNNEL_URL" ]] && die "Tunnel URL not found — check: journalctl -u pensieve-tunnel"
  echo "$TUNNEL_URL" | sudo tee "$SVC_URL_FILE" > /dev/null
  ok "Quick tunnel active: $TUNNEL_URL"
fi

# ── 6. done ───────────────────────────────────────────────────────────────────
hdr "Step 6/6 — Final step (you do this one)"
echo ""
echo -e "  ${GRN}Everything is running.${NC}"
echo ""
echo "  Go to: console.twilio.com"
echo "    → Phone Numbers → Manage → Active Numbers → your number → Messaging"
echo ""
echo "  Set 'A message comes in' to:"
echo ""
echo -e "    ${YLW}Webhook   POST   ${TUNNEL_URL}/sms${NC}"
echo ""
echo "  Hit Save. Then text your Twilio number. That's it."
echo ""
echo -e "  ${BLU}Note:${NC} The tunnel URL changes if this machine reboots."
echo "  After a reboot, run:  cat ${SVC_URL_FILE}"
echo "  and update the Twilio webhook if the URL changed."
echo ""
echo "  Useful commands:"
echo "    systemctl status pensieve-flask"
echo "    systemctl status pensieve-tunnel"
echo "    journalctl -fu pensieve-flask"
echo "    cat $SVC_URL_FILE"
echo ""
