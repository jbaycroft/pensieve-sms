# pensieve-sms

SMS-to-queue ingestion for the Pensieve vault.
Text a task to your Twilio number → lands in your FIFO queue.

## Message format

```
[!!|!] [N:] [domain:] task text
```

| Prefix | Effect |
|---|---|
| `!!` | Urgent → HEAD of queue |
| `!` | High → position 2 |
| *(none)* | Normal → FIFO tail |
| `5:` | Sets est_min to 5 (any integer) |
| `h:` / `w:` / `p:` / `f:` / `ho:` / `c:` | Domain override |

**Examples:**
```
buy CO2 sensor                      → normal, domain inferred, 30 min
5: h: calibrate pH probe            → normal, hydroponics, 5 min
!! w: deploy hotfix                 → urgent → HEAD, work, 30 min
! 10: pick up dog food              → high, domain inferred, 10 min
```

## Local dev setup

```bash
git clone https://github.com/YOUR_USERNAME/pensieve-sms
cd pensieve-sms
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements-dev.txt
cp .env.example .env
# Edit .env: set VAULT_ROOT, ENHANCE_MOCK=1 to skip LLM
python flask_ingress.py
```

## Test without Twilio

```bash
curl -X POST http://localhost:5005/test \
  -H "Content-Type: application/json" \
  -d "{\"body\": \"h: check pH\", \"from\": \"+15550001111\"}"
```

Response:
```json
{"ack": "On it.", "enhanced": "Check pH levels", "ticket_id": "TKT-202608221740"}
```

## Run tests

```bash
pytest tests/ -v
```

## Architecture

```
Phone → Twilio → Cloudflare Tunnel → Flask (this repo) → Pensieve vault
```

No cloud compute. Everything runs on your Arch box.
See `Dev/SMS Ingest Spec.md` in the vault for the full spec.

## Deploy to Arch

```bash
# On Arch box:
git clone https://github.com/YOUR_USERNAME/pensieve-sms ~/pensieve-sms
cd ~/pensieve-sms
bash deploy/install.sh
```

Edit `/etc/pensieve.env` with real values, then:
```bash
systemctl restart pensieve-flask
systemctl status pensieve-flask
```
