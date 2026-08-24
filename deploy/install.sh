#!/usr/bin/env bash
# â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
# â•‘          The Burrow â€” end-to-end Arch Linux installer           â•‘
# â•‘          theburrow.house  Â·  pensieve-sms  Â·  2026              â•‘
# â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#
# Run as your regular user (sudo called as needed).
# Everything is handled. Just answer the prompts.
set -euo pipefail

# â”€â”€ colours & helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
GRN='\033[0;32m'; YLW='\033[1;33m'; BLU='\033[0;34m'
RED='\033[0;31m'; CYN='\033[0;36m'; NC='\033[0m'
hdr()  { echo -e "\n${BLU}â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”${NC}"; echo -e "${BLU}  $1${NC}"; echo -e "${BLU}â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”${NC}"; }
ok()   { echo -e "  ${GRN}âœ“${NC}  $1"; }
warn() { echo -e "  ${YLW}!${NC}  $1"; }
info() { echo -e "  ${CYN}â†’${NC}  $1"; }
die()  { echo -e "\n  ${RED}âœ—  ERROR: $1${NC}\n"; exit 1; }

ask() {
  local var="$1" desc="$2" ex="${3:-}"
  echo -e "\n  ${YLW}${desc}${NC}"
  [[ -n "$ex" ]] && echo -e "  ${CYN}Example: ${ex}${NC}"
  read -r -p "  â–¶ " val
  [[ -z "$val" ]] && die "Value required for ${var}"
  printf '%s=%s\n' "$var" "$val"
}

ask_val() {
  # Like ask but returns raw value into a variable, not KEY=VAL
  local _desc="$1" _ex="${2:-}" _ret
  echo -e "\n  ${YLW}${_desc}${NC}"
  [[ -n "$_ex" ]] && echo -e "  ${CYN}Example: ${_ex}${NC}"
  read -r -p "  â–¶ " _ret
  echo "$_ret"
}

REPO_DIR="$HOME/pensieve-sms"
ENV_FILE="/etc/pensieve.env"
TUNNEL_NAME="theburrow"
DOMAIN="theburrow.house"
HUB_HOST="hub.${DOMAIN}"
SMS_HOST="sms.${DOMAIN}"

# â”€â”€ banner â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo ""
echo -e "${BLU}â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—${NC}"
echo -e "${BLU}â•‘          The Burrow â€” end-to-end installer                  â•‘${NC}"
echo -e "${BLU}â•‘          theburrow.house  Â·  pensieve-sms                   â•‘${NC}"
echo -e "${BLU}â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•${NC}"
echo ""
echo "  This script will configure everything:"
echo ""
echo "    1.  System dependencies (python, git, avahi, cloudflared)"
echo "    2.  Hostname â†’ pensieve  (local access: pensieve.local)"
echo "    3.  Clone pensieve-sms repo"
echo "    4.  Python virtualenv + dependencies"
echo "    5.  Collect all credentials"
echo "    6.  Write /etc/pensieve.env (mode 600)"
echo "    7.  Flask systemd service"
echo "    8.  Cloudflare named tunnel"
echo "         hub.theburrow.house  â†’ PWA (Cloudflare Access / Google Auth)"
echo "         sms.theburrow.house  â†’ Twilio webhook (open)"
echo "    9.  Cloudflare Access policy (hub only)"
echo "    10. Verification + final summary"
echo ""
read -r -p "  Press Enter to beginâ€¦"

# â”€â”€ 1. system check â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
hdr "Step 1/10 â€” System check"
[[ "$(id -u)" -eq 0 ]] && die "Run as a regular user, not root."
[[ -f /etc/arch-release ]] || warn "Not detected as Arch â€” continuing anyway."
ping -c1 -W3 8.8.8.8 &>/dev/null || die "No internet connectivity."
ok "Running as ${USER} with internet access"

# â”€â”€ 2. system dependencies â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
hdr "Step 2/10 â€” System dependencies"
sudo pacman -Sy --needed --noconfirm \
  git curl python python-pip avahi nss-mdns \
  2>&1 | grep -E '(installing|upgrading|nothing to do|error)' || true
ok "Core packages ready"

# cloudflared â€” try yay/paru first, then direct binary
if ! command -v cloudflared &>/dev/null; then
  echo "  Installing cloudflaredâ€¦"
  if command -v yay &>/dev/null; then
    yay -S --noconfirm cloudflared
  elif command -v paru &>/dev/null; then
    paru -S --noconfirm cloudflared
  else
    CFVER=$(curl -s https://api.github.com/repos/cloudflare/cloudflared/releases/latest \
      | python3 -c "import sys,json; print(json.load(sys.stdin)['tag_name'])" 2>/dev/null)
    [[ -z "$CFVER" ]] && die "Could not fetch cloudflared version"
    curl -sL "https://github.com/cloudflare/cloudflared/releases/download/${CFVER}/cloudflared-linux-amd64" \
      -o /tmp/cloudflared
    sudo install -m 755 /tmp/cloudflared /usr/local/bin/cloudflared
    ok "cloudflared ${CFVER} installed from binary"
  fi
fi
ok "cloudflared $(cloudflared --version | head -1)"

# â”€â”€ 3. hostname + mDNS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
hdr "Step 3/10 â€” Hostname + mDNS (pensieve.local)"
sudo hostnamectl set-hostname pensieve
ok "Hostname set to: pensieve"

# Enable mDNS resolution
if ! grep -q 'mdns4_minimal' /etc/nsswitch.conf; then
  sudo sed -i 's/^hosts:.*/hosts: mymachines mdns4_minimal [NOTFOUND=return] resolve [!UNAVAIL=return] files myhostname dns/' \
    /etc/nsswitch.conf
  ok "nsswitch.conf updated for mDNS"
fi

sudo systemctl enable --now avahi-daemon 2>/dev/null && ok "avahi-daemon running" \
  || warn "avahi-daemon may already be running"

info "This machine is now reachable at pensieve.local on your WiFi"

# â”€â”€ 4. repo â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
hdr "Step 4/10 â€” Repo"
if [[ -d "$REPO_DIR/.git" ]]; then
  git -C "$REPO_DIR" pull --ff-only
  ok "Repo updated"
else
  git clone git@github.com:jbaycroft/pensieve-sms.git "$REPO_DIR"
  ok "Repo cloned to $REPO_DIR"
fi

# â”€â”€ 5. python venv â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
hdr "Step 5/10 â€” Python virtualenv"
python3 -m venv "$REPO_DIR/.venv"
"$REPO_DIR/.venv/bin/pip" install --upgrade pip -q
"$REPO_DIR/.venv/bin/pip" install -r "$REPO_DIR/requirements.txt" -q
ok "Dependencies installed"

# â”€â”€ 6. credentials â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
hdr "Step 6/10 â€” Credentials"
echo ""
echo "  You will be prompted for each value."
echo "  Sources:"
echo "    Twilio   â†’ console.twilio.com â†’ Account Info (top right)"
echo "    Gemini   â†’ aistudio.google.com/apikey"
echo "    Cloudflare API â†’ dash.cloudflare.com â†’ My Profile â†’ API Tokens"
echo "               Token needs: Zone:Read, DNS:Edit, Access:Edit, Account:Read"
echo "    Cloudflare Account ID â†’ dash.cloudflare.com â†’ any zone â†’ right sidebar"
echo ""

ENV=""
ENV+=$(ask TWILIO_ACCOUNT_SID  "Twilio Account SID"                  "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")$'\n'
ENV+=$(ask TWILIO_AUTH_TOKEN    "Twilio Auth Token"                   "(from Twilio Console â†’ Account Info)")$'\n'
ENV+=$(ask TWILIO_FROM_NUMBER   "Your Twilio phone number (E.164)"    "+12035550100")$'\n'
ENV+=$(ask SMS_ALLOWLIST        "Your personal cell (E.164)"          "+12035551234")$'\n'
ENV+=$(ask JEANNIE_NUMBER       "Jeannie's cell (E.164)"              "+12035559876")$'\n'
ENV+=$(ask GEMINI_API_KEY       "Gemini API key"                      "AIzaSy...")$'\n'
ENV+=$(ask VAULT_ROOT           "Full path to Pensieve vault on this machine" "$HOME/vault/Pensieve")$'\n'
ENV+="ENHANCE_MOCK=0"$'\n'
ENV+="TEST_ENDPOINT_ENABLED=0"$'\n'

# Cloudflare â€” stored separately (not in ENV_FILE, used only during setup)
CF_ACCOUNT_ID=$(ask_val "Cloudflare Account ID" "found in dash.cloudflare.com â†’ right sidebar of any zone")
CF_API_TOKEN=$(ask_val  "Cloudflare API Token"   "create at dash.cloudflare.com â†’ My Profile â†’ API Tokens")
JOHN_EMAIL=$(ask_val    "John's Google email (for Cloudflare Access)"    "john@gmail.com")
JEANNIE_EMAIL=$(ask_val "Jeannie's Google email (for Cloudflare Access)" "jeannie@gmail.com")

# â”€â”€ 7. write env file â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
hdr "Step 7/10 â€” Writing /etc/pensieve.env"
printf '%s' "$ENV" | sudo tee "$ENV_FILE" > /dev/null
sudo chmod 600 "$ENV_FILE"
ok "Credentials written to $ENV_FILE (chmod 600, readable only by root)"

# â”€â”€ 8. flask systemd service â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
hdr "Step 8/10 â€” Flask service"

# Generate service file dynamically (paths depend on $USER and $HOME)
sudo tee /etc/systemd/system/pensieve-flask.service > /dev/null <<UNIT
[Unit]
Description=The Burrow â€” Pensieve Flask (SMS + PWA)
After=network.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
User=${USER}
WorkingDirectory=${REPO_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${REPO_DIR}/.venv/bin/python flask_ingress.py
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
sleep 2

if systemctl is-active --quiet pensieve-flask; then
  ok "Flask running on 127.0.0.1:5005"
else
  die "Flask failed â€” check: journalctl -u pensieve-flask"
fi

# Verify routes
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5005/)
[[ "$HTTP_CODE" == "200" ]] && ok "GET / â†’ 200 OK" \
  || warn "GET / returned ${HTTP_CODE} â€” check logs if tunnel fails later"

# â”€â”€ 9. cloudflare tunnel â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
hdr "Step 9/10 â€” Cloudflare Tunnel (theburrow.house)"
echo ""
echo "  A browser URL will appear below. Open it to authenticate."
echo "  If running headless (SSH), copy the URL and open it on another machine."
echo ""
cloudflared tunnel login
ok "Cloudflare login complete"

# Create tunnel (idempotent)
cloudflared tunnel create "$TUNNEL_NAME" 2>/dev/null \
  && ok "Tunnel '${TUNNEL_NAME}' created" \
  || ok "Tunnel '${TUNNEL_NAME}' already exists"

# Get tunnel ID
TUNNEL_ID=$(cloudflared tunnel list --output json \
  | python3 -c "
import sys, json
tunnels = json.load(sys.stdin)
match = [t for t in tunnels if t['name'] == '${TUNNEL_NAME}']
print(match[0]['id'] if match else '')
" 2>/dev/null)
[[ -z "$TUNNEL_ID" ]] && die "Could not get tunnel ID"
ok "Tunnel ID: $TUNNEL_ID"

# Write cloudflared config â€” both subdomains in one tunnel
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
ok "cloudflared config written"

# Route DNS for both subdomains
cloudflared tunnel route dns "$TUNNEL_NAME" "$HUB_HOST" \
  && ok "DNS routed: ${HUB_HOST}" \
  || warn "DNS routing for ${HUB_HOST} may already exist"

cloudflared tunnel route dns "$TUNNEL_NAME" "$SMS_HOST" \
  && ok "DNS routed: ${SMS_HOST}" \
  || warn "DNS routing for ${SMS_HOST} may already exist"

# Tunnel systemd service
sudo tee /etc/systemd/system/pensieve-tunnel.service > /dev/null <<UNIT
[Unit]
Description=The Burrow â€” Cloudflare Named Tunnel (theburrow.house)
After=network.target pensieve-flask.service
Requires=pensieve-flask.service
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
User=${USER}
ExecStart=/usr/bin/cloudflared tunnel \
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
sleep 4

if systemctl is-active --quiet pensieve-tunnel; then
  ok "Tunnel running"
else
  die "Tunnel failed â€” check: journalctl -u pensieve-tunnel"
fi

# â”€â”€ 10. cloudflare access (hub only) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
hdr "Step 10/10 â€” Cloudflare Access (hub.theburrow.house)"
echo "  Configuring Google-auth-gated access to the PWAâ€¦"

# Create Access application
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
  }")

CF_APP_ID=$(echo "$CF_APP_JSON" | python3 -c \
  "import sys,json; r=json.load(sys.stdin); print(r.get('result',{}).get('id',''))" 2>/dev/null)

if [[ -n "$CF_APP_ID" ]]; then
  ok "Access application created (id: ${CF_APP_ID})"

  # Create allow policy for both emails
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
    }" > /dev/null
  ok "Access policy created â€” ${JOHN_EMAIL} + ${JEANNIE_EMAIL}"
else
  warn "Access app creation failed â€” check API token permissions."
  warn "You can configure Access manually at: dash.cloudflare.com â†’ Zero Trust â†’ Access"
fi

# â”€â”€ twilio webhook update reminder â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo ""
echo "  Updating Twilio webhookâ€¦"
# Extract Twilio creds from ENV_FILE
_SID=$(sudo grep "^TWILIO_ACCOUNT_SID=" "$ENV_FILE" | cut -d= -f2)
_TOK=$(sudo grep "^TWILIO_AUTH_TOKEN=" "$ENV_FILE" | cut -d= -f2)
_NUM=$(sudo grep "^TWILIO_FROM_NUMBER=" "$ENV_FILE" | cut -d= -f2)

# Look up Phone Number SID
_PNSID=$(curl -s -u "${_SID}:${_TOK}" \
  "https://api.twilio.com/2010-04-01/Accounts/${_SID}/IncomingPhoneNumbers.json" \
  | python3 -c "
import sys, json, urllib.parse
data = json.load(sys.stdin)
nums = data.get('incoming_phone_numbers', [])
target = '${_NUM}'.replace(' ','')
match = next((n for n in nums if n['phone_number'].replace(' ','') == target), None)
print(match['sid'] if match else '')
" 2>/dev/null)

if [[ -n "$_PNSID" ]]; then
  curl -s -X POST -u "${_SID}:${_TOK}" \
    "https://api.twilio.com/2010-04-01/Accounts/${_SID}/IncomingPhoneNumbers/${_PNSID}.json" \
    --data-urlencode "SmsUrl=https://${SMS_HOST}/sms" \
    --data-urlencode "SmsMethod=POST" > /dev/null
  ok "Twilio webhook set â†’ https://${SMS_HOST}/sms"
else
  warn "Could not auto-configure Twilio. Set manually:"
  warn "  console.twilio.com â†’ your number â†’ Messaging â†’ Webhook"
  warn "  POST  https://${SMS_HOST}/sms"
fi

# â”€â”€ final summary â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo ""
echo -e "${GRN}â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—${NC}"
echo -e "${GRN}â•‘               INSTALLATION COMPLETE                         â•‘${NC}"
echo -e "${GRN}â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•${NC}"
echo ""
echo -e "  ${CYN}Services${NC}"
echo "    pensieve-flask   â†’ systemctl status pensieve-flask"
echo "    pensieve-tunnel  â†’ systemctl status pensieve-tunnel"
echo ""
echo -e "  ${CYN}URLs${NC}"
echo -e "    PWA (home, authenticated) â†’ ${YLW}https://${HUB_HOST}${NC}"
echo -e "    SMS webhook               â†’ ${YLW}https://${SMS_HOST}/sms${NC}"
echo -e "    Local (home WiFi)         â†’ ${YLW}http://pensieve.local:5005${NC}"
echo ""
echo -e "  ${CYN}Add to Home Screen${NC}"
echo "    iPhone:  Safari â†’ Share â†’ Add to Home Screen"
echo "    Android: Chrome â†’ â‹® â†’ Add to Home Screen"
echo ""
echo -e "  ${YLW}One manual step remaining â€” Google Identity Provider:${NC}"
echo ""
echo "    1. Go to: console.cloud.google.com"
echo "       APIs & Services â†’ Credentials â†’ Create â†’ OAuth 2.0 Client"
echo "       Application type: Web"
echo "       Authorised redirect URI:"

# Get CF team domain
CF_TEAM=$(curl -s \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/access/organizations" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('result',{}).get('auth_domain','<your-team>.cloudflareaccess.com'))" 2>/dev/null)

echo "         https://${CF_TEAM}/cdn-cgi/access/callback"
echo ""
echo "    2. Copy the Client ID and Client Secret"
echo ""
echo "    3. Go to: dash.cloudflare.com â†’ Zero Trust â†’ Settings â†’ Authentication"
echo "       Add identity provider â†’ Google"
echo "       Paste Client ID + Secret â†’ Save"
echo ""
echo "    4. Done. hub.theburrow.house will prompt Google login on first visit."
echo ""
echo -e "  ${CYN}Useful commands${NC}"
echo "    journalctl -fu pensieve-flask"
echo "    journalctl -fu pensieve-tunnel"
echo "    sudo cat /etc/pensieve.env"
echo "    systemctl restart pensieve-flask pensieve-tunnel"
echo ""

