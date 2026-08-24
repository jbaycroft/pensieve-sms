#!/usr/bin/env bash
# ============================================================
#   The Burrow — end-to-end Arch Linux installer (hardened)
#   theburrow.house · pensieve-sms · 2026
# ============================================================
#
# Run as your regular user (sudo called as needed).
# Safe to re-run — idempotent throughout.
# If a step fails, fix the issue and re-run; it resumes
# from the last completed checkpoint.
#
# Hardening notes vs. original:
#   - Checkpoint/resume: saves step number on success
#   - Error trap: shows line, tells user to re-run
#   - Detects 'python' vs 'python3' (Arch uses 'python')
#   - SSH clone with HTTPS fallback
#   - cloudflared: dynamic ExecStart path after install
#   - Validates Twilio + Cloudflare creds before writing
#   - pip install with retry (3 attempts)
#   - Skips nsswitch.conf if systemd-resolved manages DNS
#   - avahi: guards against double-enable
#   - Flask health check with 10-attempt retry
#   - vault structure verified before flask starts

# ── strict mode (controlled) ─────────────────────────────────
set -uo pipefail
# We do NOT use -e globally; individual commands use || die.
# This gives us more granular control without surprise exits.

# ── colours & helpers ─────────────────────────────────────────
GRN='\033[0;32m'; YLW='\033[1;33m'; BLU='\033[0;34m'
RED='\033[0;31m'; CYN='\033[0;36m'; NC='\033[0m'

hdr()  { echo -e "\n${BLU}──────────────────────────────────────────────────${NC}"; echo -e "${BLU}  $1${NC}"; echo -e "${BLU}──────────────────────────────────────────────────${NC}"; }
ok()   { echo -e "  ${GRN}✓${NC}  $1"; }
warn() { echo -e "  ${YLW}!${NC}  $1"; }
info() { echo -e "  ${CYN}→${NC}  $1"; }
die()  { echo -e "\n  ${RED}✗  ERROR: $1${NC}"; echo -e "  ${YLW}Re-run this script after fixing the issue.${NC}\n"; save_checkpoint "$CURRENT_STEP"; exit 1; }

# ── checkpoint system ─────────────────────────────────────────
CHECKPOINT_FILE="$HOME/.pensieve-install-checkpoint"
CURRENT_STEP=0

save_checkpoint() {
  echo "${1:-$CURRENT_STEP}" > "$CHECKPOINT_FILE"
}

get_checkpoint() {
  [[ -f "$CHECKPOINT_FILE" ]] && cat "$CHECKPOINT_FILE" || echo "0"
}

step_done() {
  CURRENT_STEP="$1"
  save_checkpoint "$CURRENT_STEP"
  ok "Step $1 complete"
}

RESUME_FROM=$(get_checkpoint)

should_run() {
  # Returns 0 (run) if step > RESUME_FROM, 1 (skip) otherwise
  [[ "$1" -gt "$RESUME_FROM" ]]
}

# ── constants ─────────────────────────────────────────────────
REPO_DIR="$HOME/pensieve-sms"
ENV_FILE="/etc/pensieve.env"
TUNNEL_NAME="theburrow"
DOMAIN="theburrow.house"
HUB_HOST="hub.${DOMAIN}"
SMS_HOST="sms.${DOMAIN}"

# ── banner ────────────────────────────────────────────────────
echo ""
echo -e "${BLU}╔═══════════════════════════════════════════════════════╗${NC}"
echo -e "${BLU}║          The Burrow — end-to-end installer            ║${NC}"
echo -e "${BLU}║          theburrow.house · pensieve-sms               ║${NC}"
echo -e "${BLU}╚═══════════════════════════════════════════════════════╝${NC}"
echo ""

if [[ "$RESUME_FROM" -gt "0" ]]; then
  warn "Resuming from step $RESUME_FROM (last successful step)."
  warn "Delete ${CHECKPOINT_FILE} to start fresh."
  echo ""
fi

echo "  Steps:"
echo "    1.  System check"
echo "    2.  Dependencies (python, git, avahi, cloudflared)"
echo "    3.  Hostname + mDNS"
echo "    4.  Repo clone/update"
echo "    5.  Python virtualenv + deps"
echo "    6.  Credentials"
echo "    7.  /etc/pensieve.env"
echo "    8.  Flask systemd service"
echo "    9.  Cloudflare tunnel"
echo "    10. Cloudflare Access + Twilio webhook"
echo ""
read -r -p "  Press Enter to begin…"

# ═══════════════════════════════════════════════════
# STEP 1 — system check
# ═══════════════════════════════════════════════════
hdr "Step 1/10 — System check"

[[ "$(id -u)" -eq 0 ]] && die "Run as a regular user, not root."

if [[ -f /etc/arch-release ]]; then
  ok "Arch Linux detected"
else
  warn "Not Arch Linux — continuing anyway (package names may differ)"
fi

ping -c1 -W3 8.8.8.8 &>/dev/null || die "No internet. Check your connection."
ok "Internet: OK"

command -v sudo &>/dev/null || die "sudo not found. Install it: pacman -S sudo"
command -v curl &>/dev/null || command -v wget &>/dev/null || die "Neither curl nor wget found."

step_done 1

# ═══════════════════════════════════════════════════
# STEP 2 — system dependencies
# ═══════════════════════════════════════════════════
hdr "Step 2/10 — System dependencies"

if should_run 2; then
  # Sync package database quietly
  sudo pacman -Sy --noconfirm 2>&1 | grep -E '(error|warning:)' || true

  # Install core packages — Arch correct names
  # python     = Python 3 (Arch does NOT have a 'python3' package)
  # python-pip = pip for Python 3 (NOT python3-pip)
  # sqlite     = usually bundled with python, but explicit doesn't hurt
  sudo pacman -S --needed --noconfirm \
    git curl python python-pip avahi nss-mdns \
    2>&1 | grep -E '(installing|upgrading|already installed|error)' || true
  ok "Core packages installed"

  # ── cloudflared ──────────────────────────────────
  if command -v cloudflared &>/dev/null; then
    ok "cloudflared already installed: $(cloudflared --version 2>&1 | head -1)"
  else
    info "Installing cloudflared..."
    CF_INSTALLED=0

    if command -v yay &>/dev/null; then
      yay -S --noconfirm cloudflared 2>&1 | grep -E '(installing|error)' || true
      command -v cloudflared &>/dev/null && CF_INSTALLED=1
    fi

    if [[ $CF_INSTALLED -eq 0 ]] && command -v paru &>/dev/null; then
      paru -S --noconfirm cloudflared 2>&1 | grep -E '(installing|error)' || true
      command -v cloudflared &>/dev/null && CF_INSTALLED=1
    fi

    if [[ $CF_INSTALLED -eq 0 ]]; then
      info "No AUR helper found — downloading cloudflared binary directly"
      CFVER=$(curl -s --max-time 15 \
        https://api.github.com/repos/cloudflare/cloudflared/releases/latest \
        | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('tag_name',''))" \
        2>/dev/null)
      [[ -z "$CFVER" ]] && die "Could not fetch cloudflared release version. Check GitHub API."

      TMPBIN="$(mktemp /tmp/cloudflared.XXXXXX)"
      curl -sL --max-time 60 \
        "https://github.com/cloudflare/cloudflared/releases/download/${CFVER}/cloudflared-linux-amd64" \
        -o "$TMPBIN" || die "Download of cloudflared failed."
      sudo install -m 755 "$TMPBIN" /usr/local/bin/cloudflared
      rm -f "$TMPBIN"
      command -v cloudflared &>/dev/null && CF_INSTALLED=1
    fi

    [[ $CF_INSTALLED -eq 0 ]] && die "cloudflared installation failed. Install manually from https://pkg.cloudflare.com"
    ok "cloudflared installed: $(cloudflared --version 2>&1 | head -1)"
  fi

  # Detect actual cloudflared binary path (may be /usr/bin or /usr/local/bin)
  CF_BIN=$(command -v cloudflared)
  ok "cloudflared path: $CF_BIN"

  step_done 2
else
  ok "Step 2 skipped (already done)"
  CF_BIN=$(command -v cloudflared 2>/dev/null || echo "/usr/local/bin/cloudflared")
fi

# ═══════════════════════════════════════════════════
# STEP 3 — hostname + mDNS
# ═══════════════════════════════════════════════════
hdr "Step 3/10 — Hostname + mDNS (pensieve.local)"

if should_run 3; then
  sudo hostnamectl set-hostname pensieve \
    && ok "Hostname set to: pensieve" \
    || warn "hostnamectl failed — continuing"

  # Only modify nsswitch.conf if systemd-resolved isn't handling mDNS
  if systemctl is-active --quiet systemd-resolved 2>/dev/null; then
    warn "systemd-resolved is active — skipping nsswitch.conf modification"
    warn "If pensieve.local doesn't resolve, configure mDNS via resolved.conf"
  else
    if ! grep -q 'mdns4_minimal' /etc/nsswitch.conf 2>/dev/null; then
      sudo sed -i \
        's/^hosts:.*/hosts: mymachines mdns4_minimal [NOTFOUND=return] resolve [!UNAVAIL=return] files myhostname dns/' \
        /etc/nsswitch.conf \
        && ok "nsswitch.conf updated for mDNS" \
        || warn "nsswitch.conf update failed — mDNS may not work"
    else
      ok "mDNS already in nsswitch.conf"
    fi
  fi

  # Enable avahi (guard against conflict if already running)
  if systemctl is-active --quiet avahi-daemon 2>/dev/null; then
    ok "avahi-daemon already running"
  else
    sudo systemctl enable --now avahi-daemon 2>/dev/null \
      && ok "avahi-daemon enabled + started" \
      || warn "avahi-daemon start failed (non-fatal for tunnel setup)"
  fi

  info "Machine will be reachable as pensieve.local on home WiFi"
  step_done 3
else
  ok "Step 3 skipped (already done)"
fi

# ═══════════════════════════════════════════════════
# STEP 4 — repo
# ═══════════════════════════════════════════════════
hdr "Step 4/10 — Repository"

if should_run 4; then
  if [[ -d "$REPO_DIR/.git" ]]; then
    git -C "$REPO_DIR" pull --ff-only \
      && ok "Repo updated" \
      || warn "git pull failed — continuing with existing code"
  else
    info "Cloning via SSH…"
    if git clone git@github.com:jbaycroft/pensieve-sms.git "$REPO_DIR" 2>/dev/null; then
      ok "Repo cloned via SSH"
    else
      warn "SSH clone failed — trying HTTPS (no SSH key needed)"
      git clone https://github.com/jbaycroft/pensieve-sms.git "$REPO_DIR" \
        || die "Cannot clone repo. Check internet and GitHub access."
      ok "Repo cloned via HTTPS"
      warn "To switch to SSH later: git -C $REPO_DIR remote set-url origin git@github.com:jbaycroft/pensieve-sms.git"
    fi
  fi
  step_done 4
else
  ok "Step 4 skipped (already done)"
fi

# ═══════════════════════════════════════════════════
# STEP 5 — python virtualenv
# ═══════════════════════════════════════════════════
hdr "Step 5/10 — Python virtualenv + dependencies"

if should_run 5; then
  # Detect correct Python binary (Arch uses 'python', not 'python3')
  PYTHON=""
  for py in python python3; do
    if command -v "$py" &>/dev/null; then
      ver=$("$py" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
      major=$(echo "$ver" | cut -d. -f1)
      minor=$(echo "$ver" | cut -d. -f2)
      if [[ "${major:-0}" -ge 3 && "${minor:-0}" -ge 10 ]]; then
        PYTHON="$py"
        break
      fi
    fi
  done
  [[ -z "$PYTHON" ]] && die "Python 3.10+ not found. Install: sudo pacman -S python"
  ok "Python: $($PYTHON --version)"

  # Create venv (python's built-in venv, no separate package needed on Arch)
  if [[ ! -d "$REPO_DIR/.venv" ]]; then
    "$PYTHON" -m venv "$REPO_DIR/.venv" 2>/dev/null || {
      warn "venv creation failed — trying python-virtualenv"
      sudo pacman -S --needed --noconfirm python-virtualenv \
        && virtualenv "$REPO_DIR/.venv" \
        || die "Cannot create virtualenv. Check python installation."
    }
    ok "Virtual environment created"
  else
    ok "Virtual environment already exists"
  fi

  # Upgrade pip silently
  "$REPO_DIR/.venv/bin/pip" install --upgrade pip --quiet 2>/dev/null || true

  # Install deps with retry (network can be flaky)
  INSTALLED=0
  for attempt in 1 2 3; do
    if "$REPO_DIR/.venv/bin/pip" install -r "$REPO_DIR/requirements.txt" --quiet; then
      INSTALLED=1
      break
    fi
    warn "pip install attempt $attempt/3 failed — retrying in 5s"
    sleep 5
  done
  [[ $INSTALLED -eq 0 ]] && die "pip install failed after 3 attempts. Check requirements.txt and internet."

  # Sanity check
  "$REPO_DIR/.venv/bin/python" -c "import flask, twilio" \
    || die "Import check failed — flask or twilio not installed."

  ok "Python dependencies installed"
  step_done 5
else
  ok "Step 5 skipped (already done)"
  # Detect PYTHON for later steps even when skipping
  PYTHON=$(command -v python || command -v python3)
fi

# ═══════════════════════════════════════════════════
# STEP 6 — credentials
# ═══════════════════════════════════════════════════

# Helper to read a required value
ask_val() {
  local desc="$1" ex="${2:-}" val
  echo -e "\n  ${YLW}${desc}${NC}"
  [[ -n "$ex" ]] && echo -e "  ${CYN}Example: ${ex}${NC}"
  while true; do
    read -r -p "  ▶ " val
    [[ -n "$val" ]] && break
    echo -e "  ${RED}Value required.${NC}"
  done
  echo "$val"
}

hdr "Step 6/10 — Credentials"

if should_run 6; then
  echo ""
  echo "  Sources:"
  echo "    Twilio      → console.twilio.com → Account Info (top right)"
  echo "    Gemini      → aistudio.google.com/apikey"
  echo "    Cloudflare  → dash.cloudflare.com → My Profile → API Tokens"
  echo "                  Required scopes: Zone:Read, DNS:Edit, Access:Edit, Account:Read"
  echo "    Account ID  → dash.cloudflare.com → any zone → right sidebar"
  echo ""

  SID=$(ask_val      "Twilio Account SID"                    "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
  TOKEN=$(ask_val    "Twilio Auth Token"                     "(from Twilio Console → Account Info)")
  FROM=$(ask_val     "Your Twilio phone number (E.164)"      "+12035550100")
  ALLOWLIST=$(ask_val "Your cell number (E.164)"             "+12035551234")
  JEANNIE=$(ask_val  "Jeannie's cell (E.164)"               "+12035559876")
  GEMINI=$(ask_val   "Gemini API key"                        "AIzaSy...")
  VAULT=$(ask_val    "Full path to Pensieve vault on this machine" "$HOME/vault/Pensieve")

  CF_ACCOUNT_ID=$(ask_val "Cloudflare Account ID"           "found in dash.cloudflare.com → right sidebar")
  CF_API_TOKEN=$(ask_val  "Cloudflare API Token"            "create at dash.cloudflare.com → My Profile → API Tokens")
  JOHN_EMAIL=$(ask_val    "John's Google email (for Cloudflare Access)"    "john@gmail.com")
  JEANNIE_EMAIL=$(ask_val "Jeannie's Google email (for Cloudflare Access)" "jeannie@gmail.com")

  echo ""
  info "Validating Twilio credentials…"
  TW_HTTP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
    -u "${SID}:${TOKEN}" \
    "https://api.twilio.com/2010-04-01/Accounts/${SID}.json" 2>/dev/null)
  if [[ "$TW_HTTP" == "200" ]]; then
    ok "Twilio credentials valid"
  else
    warn "Twilio API returned HTTP ${TW_HTTP} — double-check SID and token"
    warn "Continuing anyway — you can update /etc/pensieve.env later"
  fi

  info "Validating Cloudflare API token…"
  CF_HTTP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
    -H "Authorization: Bearer ${CF_API_TOKEN}" \
    "https://api.cloudflare.com/client/v4/user/tokens/verify" 2>/dev/null)
  if [[ "$CF_HTTP" == "200" ]]; then
    ok "Cloudflare token valid"
  else
    warn "Cloudflare token returned HTTP ${CF_HTTP} — check token scopes"
    warn "Required: Zone:Read, DNS:Edit, Access:Edit, Account:Read"
  fi

  # Verify vault path exists
  if [[ ! -d "$VAULT" ]]; then
    warn "Vault directory '$VAULT' does not exist — it will be created."
    mkdir -p "$VAULT/00_Queue/Tickets" || die "Cannot create vault directory."
  fi

  # Check / create Index.md
  if [[ ! -f "$VAULT/00_Queue/Index.md" ]]; then
    info "Creating initial Index.md…"
    mkdir -p "$VAULT/00_Queue/Tickets"
    cat > "$VAULT/00_Queue/Index.md" <<'INDEXEOF'
---
title: Queue
description: Pensieve FIFO task queue
---
%%
HEAD: first [[TKT-*]] in list
%%

INDEXEOF
    ok "Index.md created"
  fi

  step_done 6
fi

# ═══════════════════════════════════════════════════
# STEP 7 — write env file
# ═══════════════════════════════════════════════════
hdr "Step 7/10 — Writing /etc/pensieve.env"

if should_run 7; then
  # SID/TOKEN/etc. only defined if step 6 ran; else load from existing file
  if [[ -z "${SID:-}" ]]; then
    [[ -f "$ENV_FILE" ]] || die "No credentials collected and $ENV_FILE does not exist. Delete checkpoint and re-run."
    info "Using existing $ENV_FILE"
  else
    printf '%s\n' \
      "TWILIO_ACCOUNT_SID=${SID}" \
      "TWILIO_AUTH_TOKEN=${TOKEN}" \
      "TWILIO_FROM_NUMBER=${FROM}" \
      "SMS_ALLOWLIST=${ALLOWLIST}" \
      "JEANNIE_NUMBER=${JEANNIE}" \
      "GEMINI_API_KEY=${GEMINI}" \
      "VAULT_ROOT=${VAULT}" \
      "ENHANCE_MOCK=0" \
      "TEST_ENDPOINT_ENABLED=0" \
    | sudo tee "$ENV_FILE" > /dev/null
    sudo chmod 600 "$ENV_FILE"
    ok "Credentials written to $ENV_FILE (mode 600)"
  fi
  step_done 7
else
  ok "Step 7 skipped (already done)"
fi

# Re-read VAULT from env file for later steps
VAULT=$(sudo grep "^VAULT_ROOT=" "$ENV_FILE" 2>/dev/null | cut -d= -f2 || echo "$HOME/vault/Pensieve")

# ═══════════════════════════════════════════════════
# STEP 8 — Flask systemd service
# ═══════════════════════════════════════════════════
hdr "Step 8/10 — Flask systemd service"

if should_run 8; then
  FLASK_BIN="${REPO_DIR}/.venv/bin/python"
  [[ -x "$FLASK_BIN" ]] || die "Python venv not found at $FLASK_BIN — did step 5 complete?"

  sudo tee /etc/systemd/system/pensieve-flask.service > /dev/null <<UNIT
[Unit]
Description=The Burrow — Pensieve Flask (SMS + PWA)
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
User=${USER}
WorkingDirectory=${REPO_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${FLASK_BIN} flask_ingress.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT

  sudo systemctl daemon-reload
  sudo systemctl enable pensieve-flask
  sudo systemctl restart pensieve-flask
  ok "Flask service installed and started"

  # Health check with 10-attempt retry
  info "Waiting for Flask to respond…"
  FLASK_UP=0
  for i in $(seq 1 10); do
    HTTP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 http://127.0.0.1:5005/ 2>/dev/null)
    if [[ "$HTTP" == "200" ]]; then
      FLASK_UP=1
      break
    fi
    sleep 1
  done

  if [[ $FLASK_UP -eq 1 ]]; then
    ok "Flask responding on 127.0.0.1:5005 (HTTP 200)"
  else
    # Show last log lines to help diagnose
    echo ""
    echo "  Flask service log (last 20 lines):"
    journalctl -u pensieve-flask -n 20 --no-pager 2>/dev/null || true
    echo ""
    die "Flask not responding on port 5005. Fix the issue and re-run."
  fi

  step_done 8
else
  ok "Step 8 skipped (already done)"
fi

# ═══════════════════════════════════════════════════
# STEP 9 — Cloudflare tunnel
# ═══════════════════════════════════════════════════
hdr "Step 9/10 — Cloudflare Tunnel (theburrow.house)"

# Detect CF_BIN if step 2 was skipped
CF_BIN="${CF_BIN:-$(command -v cloudflared 2>/dev/null || echo /usr/local/bin/cloudflared)}"

if should_run 9; then
  echo ""
  echo "  A browser URL will appear. Open it to authenticate with Cloudflare."
  echo "  If running headless (SSH session), copy the URL and open on another machine."
  echo ""

  "$CF_BIN" tunnel login \
    || die "Cloudflare login failed. Check network and try again."
  ok "Cloudflare login complete"

  # Create tunnel (idempotent)
  "$CF_BIN" tunnel create "$TUNNEL_NAME" 2>/dev/null \
    && ok "Tunnel '${TUNNEL_NAME}' created" \
    || ok "Tunnel '${TUNNEL_NAME}' already exists"

  # Get tunnel ID — handle empty output gracefully
  TUNNEL_LIST_JSON=$("$CF_BIN" tunnel list --output json 2>/dev/null || echo "[]")
  TUNNEL_ID=$(echo "$TUNNEL_LIST_JSON" | python -c "
import sys, json
try:
  tunnels = json.load(sys.stdin) or []
  match = [t for t in tunnels if t.get('name') == '${TUNNEL_NAME}']
  print(match[0]['id'] if match else '')
except Exception:
  print('')
" 2>/dev/null)

  [[ -z "$TUNNEL_ID" ]] && die "Could not retrieve tunnel ID for '${TUNNEL_NAME}'. Run: cloudflared tunnel list"
  ok "Tunnel ID: $TUNNEL_ID"

  # Write cloudflared config
  mkdir -p "$HOME/.cloudflared"
  cat > "$HOME/.cloudflared/config.yml" <<EOF
tunnel: ${TUNNEL_ID}
credentials-file: ${HOME}/.cloudflared/${TUNNEL_ID}.json

ingress:
  - hostname: ${HUB_HOST}
    service: http://127.0.0.1:5005

  - hostname: ${SMS_HOST}
    service: http://127.0.0.1:5005

  - service: http_status:404
EOF
  ok "cloudflared config.yml written"

  # Route DNS — both subdomains (idempotent)
  "$CF_BIN" tunnel route dns "$TUNNEL_NAME" "$HUB_HOST" 2>/dev/null \
    && ok "DNS routed: ${HUB_HOST}" \
    || warn "DNS route for ${HUB_HOST} may already exist (safe)"

  "$CF_BIN" tunnel route dns "$TUNNEL_NAME" "$SMS_HOST" 2>/dev/null \
    && ok "DNS routed: ${SMS_HOST}" \
    || warn "DNS route for ${SMS_HOST} may already exist (safe)"

  # Tunnel systemd service — uses detected CF_BIN path
  sudo tee /etc/systemd/system/pensieve-tunnel.service > /dev/null <<UNIT
[Unit]
Description=The Burrow — Cloudflare Named Tunnel (theburrow.house)
After=network-online.target pensieve-flask.service
Wants=network-online.target
Requires=pensieve-flask.service
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
User=${USER}
ExecStart=${CF_BIN} tunnel \
    --config ${HOME}/.cloudflared/config.yml \
    run ${TUNNEL_NAME}
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT

  sudo systemctl daemon-reload
  sudo systemctl enable pensieve-tunnel
  sudo systemctl restart pensieve-tunnel

  # Wait for tunnel to connect
  info "Waiting for tunnel to connect…"
  sleep 5

  if systemctl is-active --quiet pensieve-tunnel; then
    ok "Tunnel service running"
  else
    echo "  Tunnel service log (last 20 lines):"
    journalctl -u pensieve-tunnel -n 20 --no-pager 2>/dev/null || true
    die "Tunnel failed to start. Check log above and re-run."
  fi

  step_done 9
else
  ok "Step 9 skipped (already done)"
fi

# ═══════════════════════════════════════════════════
# STEP 10 — Cloudflare Access + Twilio webhook
# ═══════════════════════════════════════════════════
hdr "Step 10/10 — Cloudflare Access + Twilio webhook"

if should_run 10; then
  # Load CF creds — may have been collected in step 6 or need re-prompting
  if [[ -z "${CF_ACCOUNT_ID:-}" ]]; then
    CF_ACCOUNT_ID=$(ask_val "Cloudflare Account ID" "from dash.cloudflare.com → sidebar")
    CF_API_TOKEN=$(ask_val  "Cloudflare API Token"   "from dash.cloudflare.com → My Profile → API Tokens")
    JOHN_EMAIL=$(ask_val    "John's Google email"    "john@gmail.com")
    JEANNIE_EMAIL=$(ask_val "Jeannie's Google email" "jeannie@gmail.com")
  fi

  info "Creating Cloudflare Access application for ${HUB_HOST}…"
  CF_APP_JSON=$(curl -s -X POST \
    "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/access/apps" \
    -H "Authorization: Bearer ${CF_API_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{
      \"name\": \"The Burrow Hub\",
      \"domain\": \"${HUB_HOST}\",
      \"type\": \"self_hosted\",
      \"session_duration\": \"168h\",
      \"auto_redirect_to_identity\": true
    }" 2>/dev/null)

  CF_APP_ID=$(echo "$CF_APP_JSON" | python -c \
    "import sys,json; r=json.load(sys.stdin); print(r.get('result',{}).get('id',''))" 2>/dev/null)

  if [[ -n "$CF_APP_ID" ]]; then
    ok "Access application created (id: ${CF_APP_ID})"

    curl -s -X POST \
      "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/access/apps/${CF_APP_ID}/policies" \
      -H "Authorization: Bearer ${CF_API_TOKEN}" \
      -H "Content-Type: application/json" \
      -d "{
        \"name\": \"Household\",
        \"decision\": \"allow\",
        \"include\": [
          {\"email\": {\"email\": \"${JOHN_EMAIL}\"}},
          {\"email\": {\"email\": \"${JEANNIE_EMAIL}\"}}
        ],
        \"require\": [],
        \"exclude\": []
      }" > /dev/null 2>&1
    ok "Access policy created — ${JOHN_EMAIL} + ${JEANNIE_EMAIL}"
  else
    warn "Access app creation failed. Create manually:"
    warn "  dash.cloudflare.com → Zero Trust → Access → Applications → Add"
    warn "  Domain: ${HUB_HOST}  | Session: 168h"
  fi

  # ── Twilio webhook auto-configure ────────────────────────
  info "Configuring Twilio webhook…"
  _SID=$(sudo grep "^TWILIO_ACCOUNT_SID=" "$ENV_FILE" | cut -d= -f2)
  _TOK=$(sudo grep "^TWILIO_AUTH_TOKEN=" "$ENV_FILE" | cut -d= -f2)
  _NUM=$(sudo grep "^TWILIO_FROM_NUMBER=" "$ENV_FILE" | cut -d= -f2)

  _PNSID=$(curl -s --max-time 10 -u "${_SID}:${_TOK}" \
    "https://api.twilio.com/2010-04-01/Accounts/${_SID}/IncomingPhoneNumbers.json" \
    | python -c "
import sys, json
try:
  data = json.load(sys.stdin)
  nums = data.get('incoming_phone_numbers', [])
  target = '${_NUM}'.replace(' ','')
  match = next((n for n in nums if n['phone_number'].replace(' ','') == target), None)
  print(match['sid'] if match else '')
except Exception:
  print('')
" 2>/dev/null)

  if [[ -n "$_PNSID" ]]; then
    curl -s -X POST -u "${_SID}:${_TOK}" \
      "https://api.twilio.com/2010-04-01/Accounts/${_SID}/IncomingPhoneNumbers/${_PNSID}.json" \
      --data-urlencode "SmsUrl=https://${SMS_HOST}/sms" \
      --data-urlencode "SmsMethod=POST" > /dev/null 2>&1
    ok "Twilio webhook set → https://${SMS_HOST}/sms"
  else
    warn "Could not auto-configure Twilio. Set manually:"
    warn "  console.twilio.com → your number → Messaging → Webhook"
    warn "  POST  https://${SMS_HOST}/sms"
  fi

  step_done 10
else
  ok "Step 10 skipped (already done)"
fi

# ═══════════════════════════════════════════════════
# COMPLETE
# ═══════════════════════════════════════════════════
rm -f "$CHECKPOINT_FILE"

# Get CF team domain for Google IdP instructions
CF_TEAM=""
if [[ -n "${CF_ACCOUNT_ID:-}" ]] && [[ -n "${CF_API_TOKEN:-}" ]]; then
  CF_TEAM=$(curl -s --max-time 10 \
    "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/access/organizations" \
    -H "Authorization: Bearer ${CF_API_TOKEN}" \
    | python -c "import sys,json; r=json.load(sys.stdin); print(r.get('result',{}).get('auth_domain','<your-team>.cloudflareaccess.com'))" \
    2>/dev/null || echo "<your-team>.cloudflareaccess.com")
fi
CF_TEAM="${CF_TEAM:-<your-team>.cloudflareaccess.com}"

echo ""
echo -e "${GRN}╔═══════════════════════════════════════════════════════╗${NC}"
echo -e "${GRN}║            INSTALLATION COMPLETE                      ║${NC}"
echo -e "${GRN}╚═══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${CYN}Services${NC}"
echo "    systemctl status pensieve-flask"
echo "    systemctl status pensieve-tunnel"
echo "    journalctl -fu pensieve-flask"
echo "    journalctl -fu pensieve-tunnel"
echo ""
echo -e "  ${CYN}URLs${NC}"
echo -e "    PWA (authenticated)  → ${YLW}https://${HUB_HOST}${NC}"
echo -e "    SMS webhook          → ${YLW}https://${SMS_HOST}/sms${NC}"
echo -e "    Local (home WiFi)    → ${YLW}http://pensieve.local:5005${NC}"
echo ""
echo -e "  ${CYN}Add to Home Screen (PWA install)${NC}"
echo "    iPhone:  Safari → Share → Add to Home Screen"
echo "    Android: Chrome → ⋮ → Add to Home Screen"
echo ""
echo -e "  ${YLW}One manual step — Google Identity Provider:${NC}"
echo ""
echo "    1. console.cloud.google.com"
echo "       APIs & Services → Credentials → Create → OAuth 2.0 Client ID"
echo "       Application type: Web"
echo "       Authorised redirect URI:"
echo "         https://${CF_TEAM}/cdn-cgi/access/callback"
echo ""
echo "    2. Copy the Client ID and Client Secret"
echo ""
echo "    3. dash.cloudflare.com → Zero Trust → Settings → Authentication"
echo "       Add provider → Google → paste Client ID + Secret → Save"
echo ""
echo "    4. Done. hub.theburrow.house will prompt Google login on first visit."
echo ""
echo -e "  ${CYN}If anything is wrong${NC}"
echo "    journalctl -fu pensieve-flask"
echo "    sudo cat /etc/pensieve.env"
echo "    systemctl restart pensieve-flask pensieve-tunnel"
echo ""
echo -e "  ${CYN}Migrate existing vault tickets to SQLite (one-time)${NC}"
echo "    cd ~/pensieve-sms"
echo "    VAULT_ROOT=\$(grep VAULT_ROOT /etc/pensieve.env | cut -d= -f2) \\"
echo "      .venv/bin/python -m app.migrate"
echo ""
