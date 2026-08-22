"""
routes/jeannie.py - Jeannie SMS handler.

Jeannie's number lives in JEANNIE_NUMBER env var only.
Called directly from sms.py dispatcher, never via HTTP routing.
"""

import logging
from twilio.twiml.messaging_response import MessagingResponse

from ..parser import parse
from ..enhancer import enhance, infer_domain
from ..vault import write_ticket, write_index
from ..ack import random_ack

log = logging.getLogger(__name__)

# Blueprint is registered in create_app but has no routes of its own.
# All routing goes through /sms which dispatches here.
from flask import Blueprint
jeannie_bp = Blueprint("jeannie", __name__)


def _twiml(msg: str):
    r = MessagingResponse()
    r.message(msg)
    return str(r), 200, {"Content-Type": "text/xml"}


def jeannie_ingest(body: str):
    """Process a message from Jeannie. Same flow as general SMS for now."""
    log.info("Jeannie ingest received")
    try:
        parsed   = parse(body)
        enhanced = enhance(parsed.raw_text, parsed.domain)
        domain   = parsed.domain or infer_domain(enhanced)
        tid      = write_ticket(enhanced, domain, parsed.priority, parsed.est_min)
        write_index(tid, parsed.priority)
        return _twiml(f"{random_ack()}\n-> {enhanced}")
    except Exception as e:
        log.error("jeannie_ingest error: %s", e, exc_info=True)
        return _twiml("Something went wrong.")
