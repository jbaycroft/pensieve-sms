"""Entry point. Run with: python flask_ingress.py"""
import os
import logging
import uuid

from dotenv import load_dotenv
load_dotenv()

# ── structured JSON logging ───────────────────────────────────────────────────
from pythonjsonlogger import jsonlogger  # type: ignore[import]

_handler = logging.StreamHandler()
_handler.setFormatter(jsonlogger.JsonFormatter(
    fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
))
logging.root.setLevel(logging.INFO)
logging.root.handlers = [_handler]

log = logging.getLogger(__name__)

# ── app factory ───────────────────────────────────────────────────────────────
from app import create_app

app = create_app()


# ── request-id middleware ─────────────────────────────────────────────────────
@app.before_request
def _attach_request_id():
    from flask import g, request
    g.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]


@app.after_request
def _stamp_request_id(response):
    from flask import g
    response.headers["X-Request-ID"] = getattr(g, "request_id", "-")
    return response


# ── startup summary (secrets masked) ─────────────────────────────────────────
def _masked(val: str) -> str:
    return val[:4] + "****" if val and len(val) > 4 else "****"


log.info(
    "Pensieve starting",
    extra={
        "vault_root": os.environ.get("VAULT_ROOT", "NOT SET"),
        "twilio_sid": _masked(os.environ.get("TWILIO_ACCOUNT_SID", "")),
        "gemini_key": _masked(os.environ.get("GEMINI_API_KEY", "")),
        "enhance_mock": os.environ.get("ENHANCE_MOCK", "0"),
        "test_endpoint": os.environ.get("TEST_ENDPOINT_ENABLED", "1"),
    },
)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5005, debug=False)
