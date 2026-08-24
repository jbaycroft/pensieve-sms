"""
routes/jeannie.py - Jeannie SMS handler.

Jeannie's number lives in JEANNIE_NUMBER env var only.
Called directly from sms.py dispatcher, never via HTTP routing.
"""

import logging
from flask import Blueprint

from .sms import _twiml, _process
from ..ack import random_ack

log = logging.getLogger(__name__)

# Blueprint is registered in create_app but has no routes of its own.
# All routing goes through /sms which dispatches here.
jeannie_bp = Blueprint("jeannie", __name__)


def jeannie_ingest(body: str) -> tuple:
    """Process a sanitised message from Jeannie. Delegates to shared sms helpers."""
    log.info("Jeannie ingest received")
    try:
        enhanced, tid = _process(body)
        return _twiml(f"{random_ack()}\n-> {enhanced}")
    except Exception as e:
        log.error("jeannie_ingest error: %s", e, exc_info=True)
        return _twiml("Something went wrong.")
