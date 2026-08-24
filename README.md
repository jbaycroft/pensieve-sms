# The Burrow — pensieve-sms

Household brain system. Runs on an Arch Linux box. Captures tasks from anywhere — SMS on the go, PWA on the couch — and queues them into an Obsidian vault.

## Table of Contents

1. [Architecture](#architecture)
2. [File Structure](#file-structure)
3. [Environment Variables](#environment-variables)
4. [SMS Message Format](#sms-message-format)
5. [PWA Quick Actions](#pwa-quick-actions)
6. [Vault Ticket Schema](#vault-ticket-schema)
7. [Queue Ordering Rules](#queue-ordering-rules)
8. [Production URLs](#production-urls)
9. [Deployment (Arch Linux)](#deployment-arch-linux)
10. [Local Development (Windows)](#local-development-windows)
11. [Running Tests](#running-tests)
12. [Troubleshooting](#troubleshooting)

---

## Architecture

```
Phone (anywhere)  ->  hub.theburrow.house  ->  Cloudflare Access (Google Auth)
                                           ->  Tunnel  ->  Flask PWA  ->  Obsidian vault

Phone (SMS)       ->  Twilio  ->  sms.theburrow.house/sms  ->  Flask  ->  Obsidian vault

Home WiFi         ->  http://pensieve.local:5005  (no auth)
```

Both ingress paths write to the same FIFO queue in the Obsidian vault (`00_Queue/`).

```
Cloudflare Tunnel (theburrow)
+-- hub.theburrow.house    -> Flask /           (Cloudflare Access, Google auth)
+-- sms.theburrow.house    -> Flask /sms        (Twilio webhook, no auth)
```

---

## File Structure

```
pensieve-sms/
+-- app/
|   +-- __init__.py          Flask app factory -- registers all blueprints
|   +-- parser.py            SMS prefix parser (!! ! N: domain:)
|   +-- enhancer.py          Gemini Flash Lite rewrite + domain inference
|   |                        ENHANCE_MOCK=1 -> returns raw text, no API call
|   +-- vault.py             Ticket writer + Index.md FIFO inserter
|   +-- ack.py               Random confirmation phrases for SMS replies
|   +-- preferences.py       Per-user preference store (JSON file)
|   +-- quick_actions.py     Quick action button definitions + custom file loader
|   +-- routes/
|       +-- sms.py           POST /sms (Twilio webhook) + POST /test (dev)
|       +-- jeannie.py       Isolated Jeannie handler -- called from sms.py
|       +-- pwa.py           All PWA routes (/, /api/*, /manifest.json, /sw.js)
+-- templates/
|   +-- base.html            Shell: HTMX + Alpine.js + Tailwind CDN + SW registration
|   +-- home.html            Main screen: user toggle, grid, priority, freeform, queue
|   +-- partials/
|       +-- queue.html       HTMX queue partial -- HEAD badge, priority colours
|       +-- action_panel.html  Expanded panel -- coffee / prefilled / freeform
+-- static/
|   +-- sw.js                Service worker -- caches shell, API calls always network
+-- tests/
|   +-- test_parser.py       Parser: all prefix combinations
|   +-- test_vault.py        Vault: ticket creation, index insertion all priorities
|   +-- test_preferences.py  Preference store: save, get, isolation, persistence
|   +-- test_quick_actions.py  Actions: defaults, custom file, fallback
|   +-- test_pwa.py          PWA routes: home, queue, panels, task/quick-action APIs
|   +-- test_sms_routes.py   SMS: /test endpoint, domain prefixes, Jeannie isolation
+-- deploy/
|   +-- install.sh           End-to-end Arch Linux installer (run once)
+-- flask_ingress.py         Entry point -- starts Flask on 127.0.0.1:5005
+-- requirements.txt
+-- .env.example
+-- .gitattributes
+-- .gitignore
```

---

## Environment Variables

All variables are collected interactively by `install.sh` and written to `/etc/pensieve.env` (mode 600). For local dev copy `.env.example` to `.env`.

| Variable | Required | Description |
|---|---|---|
| `TWILIO_ACCOUNT_SID` | yes | `ACxxxxxxxx...` from Twilio Console -> Account Info |
| `TWILIO_AUTH_TOKEN` | yes | From Twilio Console -> Account Info |
| `TWILIO_FROM_NUMBER` | yes | Your Twilio number in E.164 (`+12035550100`) |
| `SMS_ALLOWLIST` | yes | John's cell in E.164 -- comma-separated if multiple |
| `JEANNIE_NUMBER` | yes | Jeannie's cell in E.164 -- **never** in `SMS_ALLOWLIST` |
| `GEMINI_API_KEY` | yes (live) | `AIzaSy...` from aistudio.google.com/apikey |
| `VAULT_ROOT` | yes | Absolute path to Pensieve vault root |
| `ENHANCE_MOCK` | no | `1` = skip Gemini, return raw text. Default: `0` |
| `TEST_ENDPOINT_ENABLED` | no | `1` = enable `POST /test`. Default: `1` (set `0` in prod) |

**Jeannie's number** is checked before the allowlist. Her messages route through `jeannie_ingest()`. She must never appear in `SMS_ALLOWLIST`.

---

## SMS Message Format

```
[priority] [time] [domain] <task text>

Priority prefix (optional, must be first):
  !!          urgent -- ticket jumps to HEAD of queue
  !           high   -- ticket inserts at position 2

Time prefix (optional, digits followed by colon):
  5:          est_min = 5 minutes
  30:         est_min = 30 minutes (default)

Domain prefix (optional):
  w:          work
  h:          hydroponics
  p:          property
  f:          physical
  ho:         hobby
  c:          connection
  (long forms also work: work:, hydroponics:, property:, physical:, hobby:, connection:)
```

### Examples

```
buy CO2 sensor                     -> normal, 30min, domain auto-inferred by Gemini
!! fix staging env vars            -> urgent, inserts at HEAD
! 5: h: check pH levels            -> high, 5min, hydroponics
w: update billing webhook          -> work domain, normal
!! 10: p: chainsaw won't start     -> urgent, 10min, property
```

---

## PWA Quick Actions

Accessible at `hub.theburrow.house` (or `pensieve.local:5005` on home WiFi).

| Button | Type | Domain | Behaviour |
|---|---|---|---|
| Coffee | coffee | connection | Full panel: size, drink, notes, remember toggle |
| Grocery | freeform | property | Text input |
| Hydro Check | prefilled | hydroponics | One-tap -- queues "Check pH / EC / water level" (15 min) |
| Dogs | freeform | property | Text input |
| Property | freeform | property | Text input |
| Custom | freeform | auto | Text input, domain auto-inferred |

### Customising actions

Create `VAULT_ROOT/.pensieve-app/quick_actions.json`. See `app/quick_actions.py` for the full schema. If the file is absent or invalid JSON, built-in defaults are used.

### Coffee preferences

Per-user preferences saved at `VAULT_ROOT/.pensieve-app/preferences.json` when "Remember" is checked. Pre-filled on next panel open.

---

## Vault Ticket Schema

```yaml
---
id: TKT-202608231423
title: Check pH levels and top off reservoir
domain: hydroponics
priority: normal          # critical | high | normal  (urgent maps to critical)
status: queued            # queued | active | done
created: 2026-08-23
energy: medium
est_min: 30
recur: false
source: sms
tags: [hydroponics, sms]
---

Check pH levels and top off reservoir
```

Files: `VAULT_ROOT/00_Queue/Tickets/TKT-YYYYMMDDHHMM.md`

---

## Queue Ordering Rules

`VAULT_ROOT/00_Queue/Index.md` holds `[[TKT-*]]` wikilinks in FIFO order. First link is HEAD.

| Priority | Insert position |
|---|---|
| `urgent` | After `%% block` -- becomes new HEAD |
| `high` | After first existing `[[link]]` -- position 2 |
| `normal` | Appended to tail |

---

## Production URLs

| URL | Purpose | Auth |
|---|---|---|
| `https://hub.theburrow.house` | PWA home screen | Cloudflare Access / Google |
| `https://sms.theburrow.house/sms` | Twilio webhook | Twilio signature |
| `http://pensieve.local:5005` | Home WiFi direct | None |

---

## Deployment (Arch Linux)

### First-time install

```bash
git clone git@github.com:jbaycroft/pensieve-sms.git ~/pensieve-sms
bash ~/pensieve-sms/deploy/install.sh
```

The installer handles 10 steps:

1. System check (Arch, internet, non-root)
2. `pacman -S git curl python python-pip avahi nss-mdns` + cloudflared
3. Hostname -> `pensieve`, avahi enabled -> `pensieve.local` on WiFi
4. Repo clone (or `git pull` if present)
5. Python venv + `pip install -r requirements.txt`
6. Interactive credential prompts (Twilio x3, allowlist, Jeannie, Gemini, VAULT_ROOT, Cloudflare API token, emails)
7. `/etc/pensieve.env` written, `chmod 600`
8. `pensieve-flask.service` installed + started + smoke-tested
9. `cloudflared tunnel login` -> creates `theburrow` tunnel -> DNS routed for both subdomains -> `pensieve-tunnel.service` started
10. Cloudflare Access app + allow policy created via API, Twilio webhook auto-configured

### One manual step after install

Google OAuth IdP setup (2 minutes in browser):

```
1. console.cloud.google.com -> APIs & Services -> Credentials
   -> Create -> OAuth 2.0 Client ID -> Web application
   Authorized redirect URI: https://<team>.cloudflareaccess.com/cdn-cgi/access/callback
   (installer prints your exact URI)

2. Copy Client ID and Client Secret

3. dash.cloudflare.com -> Zero Trust -> Settings -> Authentication
   -> Add provider -> Google -> paste ID + Secret -> Save
```

### Adding to home screen (PWA install)

- iPhone: Safari -> Share -> Add to Home Screen
- Android: Chrome -> menu -> Add to Home Screen

### Updating

```bash
cd ~/pensieve-sms && git pull
sudo systemctl restart pensieve-flask
```

### Service management

```bash
systemctl status pensieve-flask
systemctl status pensieve-tunnel
journalctl -fu pensieve-flask
journalctl -fu pensieve-tunnel
sudo systemctl restart pensieve-flask pensieve-tunnel
```

---

## Local Development (Windows)

```powershell
cd c:\vaults\pensieve-sms

# First time
Copy-Item .env.example .env
# Edit .env: ENHANCE_MOCK=1, TEST_ENDPOINT_ENABLED=1, VAULT_ROOT=c:\vaults\Pensieve

python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python flask_ingress.py
# -> http://localhost:5005
```

### Testing SMS without Twilio

```powershell
$body = '{"body": "h: check pH", "from": "+15550001234"}'
Invoke-RestMethod http://localhost:5005/test -Method POST -ContentType application/json -Body $body
```

```bash
curl -X POST http://localhost:5005/test \
  -H "Content-Type: application/json" \
  -d '{"body": "!! fix prod deploy"}'
```

---

## Running Tests

```bash
.venv\Scripts\python -m pytest tests/ -v
```

All 96 tests pass in < 2 seconds. No external services required.

| File | Tests | Covers |
|---|---|---|
| `test_parser.py` | 10 | All prefix combinations, edge cases |
| `test_vault.py` | 5 | Ticket creation, HEAD/high/normal insertion |
| `test_preferences.py` | 11 | Empty state, save/get, isolation, file persistence |
| `test_quick_actions.py` | 13 | Defaults, custom file, invalid JSON fallback |
| `test_pwa.py` | 39 | Home, queue, panels, task/quick-action APIs, preferences, manifest, SW |
| `test_sms_routes.py` | 18 | /test endpoint, all domain prefixes, Jeannie isolation, queue ordering |

---

## Troubleshooting

### Flask won't start

```bash
journalctl -u pensieve-flask
sudo cat /etc/pensieve.env
```
- `VAULT_ROOT` must exist with `00_Queue/Index.md` inside
- All 7 env vars must be present

### Tunnel not connecting

```bash
journalctl -u pensieve-tunnel
cloudflared tunnel list
cat ~/.cloudflared/config.yml
cloudflared tunnel login   # re-auth if cert expired
```

Re-add DNS routes (idempotent):
```bash
cloudflared tunnel route dns theburrow hub.theburrow.house
cloudflared tunnel route dns theburrow sms.theburrow.house
```

### Twilio webhook 403

- `TWILIO_AUTH_TOKEN` must match Twilio Console exactly
- Webhook URL must be `POST https://sms.theburrow.house/sms`

### Jeannie's SMS not creating tickets

- `JEANNIE_NUMBER` must be E.164 and **not** in `SMS_ALLOWLIST`
- Check logs for `"Jeannie ingest received"`

### Queue stale in PWA

```bash
curl http://localhost:5005/api/queue
```
- `VAULT_ROOT` must point to same vault Obsidian uses
- Verify vault sync is running on Windows dev machine

### PWA won't install to home screen

- iPhone requires Safari
- Must be HTTPS in production (`hub.theburrow.house`, not `pensieve.local`)

### Cloudflare Access infinite redirect

- Google IdP not yet configured -- see manual step above
- Authorized email must match exactly (case-sensitive)
- Session is 168h -- re-auth required weekly

### `sms.theburrow.house` not working

- Both subdomains are in the same tunnel config -- check `~/.cloudflared/config.yml`
- `sms` subdomain bypasses Access and goes direct to Flask `/sms`
- Re-add DNS route if missing (see above)

### Services down after reboot

```bash
sudo systemctl enable pensieve-flask pensieve-tunnel
```

### Preferences not saving

```bash
ls $VAULT_ROOT/.pensieve-app/
cat $VAULT_ROOT/.pensieve-app/preferences.json
```
- Directory is auto-created on first save
- Vault path must be writable by the Flask user

### Re-running install.sh

Safe and idempotent -- `--needed` skips installed packages, tunnel create and DNS route are no-ops if already present.
