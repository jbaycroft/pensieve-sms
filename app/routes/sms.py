"""
routes/sms.py - /sms webhook (Twilio) and /test dev endpoint.

/test bypasses Twilio signature validation for local testing.
Disable in prod with TEST_ENDPOINT_ENABLED=0.
"""

import os
import re
import logging
from flask import Blueprint, request, jsonify, Response
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

from ..parser import parse
from ..enhancer import enhance, infer_domain
from ..vault import write_ticket, write_index
from ..ack import random_ack

log = logging.getLogger(__name__)
sms_bp = Blueprint("sms", __name__)

TWILIO_TOKEN    = os.environ.get("TWILIO_AUTH_TOKEN", "")
ALLOWED_NUMBERS = set(filter(None, os.environ.get("SMS_ALLOWLIST", "").split(",")))
JEANNIE_NUMBER  = os.environ.get("JEANNIE_NUMBER", "")

_MAX_BODY_LEN = 500
_NON_PRINTABLE = re.compile(r"[^\x09\x0a\x0d\x20-\x7e\x80-\xff]")


def _sanitise(text: str) -> str:
    """Strip non-printable control characters; hard-cap at _MAX_BODY_LEN."""
    cleaned = _NON_PRINTABLE.sub("", text)
    return cleaned[:_MAX_BODY_LEN]


def _twiml(msg: str) -> tuple[str, int, dict]:
    r = MessagingResponse()
    r.message(msg)
    return str(r), 200, {"Content-Type": "text/xml"}


def _process(body: str) -> tuple[str, str]:
    """parse → enhance → write → return (enhanced_title, ticket_id)."""
    parsed   = parse(body)
    enhanced = enhance(parsed.raw_text, parsed.domain)
    domain   = parsed.domain or infer_domain(enhanced)
    tid      = write_ticket(enhanced, domain, parsed.priority, parsed.est_min)
    write_index(tid, parsed.priority)
    return enhanced, tid


@sms_bp.route("/sms", methods=["POST"])
def sms_ingest() -> Response:
    validator = RequestValidator(TWILIO_TOKEN)
    if not validator.validate(
        request.url,
        request.form,
        request.headers.get("X-Twilio-Signature", ""),
    ):
        log.warning("Invalid Twilio signature from %s", request.remote_addr)
        return "Forbidden", 403  # type: ignore[return-value]

    from_num = request.form.get("From", "")
    raw_body = request.form.get("Body", "").strip()

    # Input validation
    if len(raw_body) > _MAX_BODY_LEN:
        log.warning("SMS body too long (%d chars) from %s — truncating", len(raw_body), from_num)
    body = _sanitise(raw_body)

    if not body:
        return _twiml("Empty message — nothing to capture.")  # type: ignore[return-value]

    # Jeannie: isolated — never touches ALLOWLIST
    if JEANNIE_NUMBER and from_num == JEANNIE_NUMBER:
        from .jeannie import jeannie_ingest
        return jeannie_ingest(body)  # type: ignore[return-value]

    if from_num not in ALLOWED_NUMBERS:
        # Mask the number in logs: show only last 4 digits
        masked = f"***{from_num[-4:]}" if len(from_num) >= 4 else "***"
        log.warning("Rejected unknown sender: %s", masked)
        return _twiml("Unknown sender.")  # type: ignore[return-value]

    try:
        enhanced, tid = _process(body)
        return _twiml(f"{random_ack()}\n-> {enhanced}")  # type: ignore[return-value]
    except Exception as e:
        log.error("sms_ingest error: %s", e, exc_info=True)
        return _twiml("Something went wrong. Ticket not created.")  # type: ignore[return-value]


@sms_bp.route("/test", methods=["POST"])
def test_ingest() -> Response:
    """
    Dev-only. POST JSON: {"body": "h: check pH", "from": "+15550001234"}
    No Twilio auth required. Always returns JSON. Disable in prod: TEST_ENDPOINT_ENABLED=0
    """
    if os.environ.get("TEST_ENDPOINT_ENABLED", "1") == "0":
        return jsonify({"error": "disabled"}), 403  # type: ignore[return-value]

    data     = request.get_json(force=True) or {}
    from_num = data.get("from", "LOCAL")
    raw_body = data.get("body", "").strip()

    if not raw_body:
        return jsonify({"error": "body required"}), 400  # type: ignore[return-value]

    if len(raw_body) > _MAX_BODY_LEN:
        return jsonify({"error": f"body exceeds {_MAX_BODY_LEN} character limit"}), 400  # type: ignore[return-value]

    body = _sanitise(raw_body)

    try:
        enhanced, tid = _process(body)
        return jsonify({"ack": random_ack(), "enhanced": enhanced, "ticket_id": tid})
    except Exception as e:
        log.error("test_ingest error: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500  # type: ignore[return-value]
