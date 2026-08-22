"""
routes/sms.py - /sms webhook (Twilio) and /test dev endpoint.

/test bypasses Twilio signature validation for local testing.
Disable in prod with TEST_ENDPOINT_ENABLED=0.
"""

import os
import logging
from flask import Blueprint, request, jsonify
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


def _twiml(msg: str):
    r = MessagingResponse()
    r.message(msg)
    return str(r), 200, {"Content-Type": "text/xml"}


def _process(body: str):
    """parse -> enhance -> write -> return (enhanced, ticket_id)"""
    parsed   = parse(body)
    enhanced = enhance(parsed.raw_text, parsed.domain)
    domain   = parsed.domain or infer_domain(enhanced)
    tid      = write_ticket(enhanced, domain, parsed.priority, parsed.est_min)
    write_index(tid, parsed.priority)
    return enhanced, tid


@sms_bp.route("/sms", methods=["POST"])
def sms_ingest():
    validator = RequestValidator(TWILIO_TOKEN)
    if not validator.validate(
        request.url,
        request.form,
        request.headers.get("X-Twilio-Signature", ""),
    ):
        log.warning("Invalid Twilio signature from %s", request.remote_addr)
        return ("Forbidden", 403)

    from_num = request.form.get("From", "")
    body     = request.form.get("Body", "").strip()

    # Jeannie: isolated — never touches ALLOWLIST
    if JEANNIE_NUMBER and from_num == JEANNIE_NUMBER:
        from .jeannie import jeannie_ingest
        return jeannie_ingest(body)

    if from_num not in ALLOWED_NUMBERS:
        log.warning("Rejected unknown sender: %s", from_num)
        return _twiml("Unknown sender.")

    try:
        enhanced, tid = _process(body)
        return _twiml(f"{random_ack()}\n-> {enhanced}")
    except Exception as e:
        log.error("sms_ingest error: %s", e, exc_info=True)
        return _twiml("Something went wrong. Ticket not created.")


@sms_bp.route("/test", methods=["POST"])
def test_ingest():
    """
    Dev-only. POST JSON: {"body": "h: check pH", "from": "+15550001234"}
    No Twilio auth required. Disable in prod: TEST_ENDPOINT_ENABLED=0
    """
    if os.environ.get("TEST_ENDPOINT_ENABLED", "1") == "0":
        return ({"error": "disabled"}, 403)

    data     = request.get_json(force=True) or {}
    from_num = data.get("from", "LOCAL")
    body     = data.get("body", "").strip()

    if not body:
        return ({"error": "body required"}, 400)

    if JEANNIE_NUMBER and from_num == JEANNIE_NUMBER:
        from .jeannie import jeannie_ingest
        return jeannie_ingest(body)

    try:
        enhanced, tid = _process(body)
        return jsonify({"ack": random_ack(), "enhanced": enhanced, "ticket_id": tid})
    except Exception as e:
        log.error("test_ingest error: %s", e, exc_info=True)
        return ({"error": str(e)}, 500)
