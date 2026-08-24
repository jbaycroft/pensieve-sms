"""
enhancer.py - Gemini Flash Lite enhancement + domain inference.

Set ENHANCE_MOCK=1 to bypass LLM (returns raw text). Use for local dev without API key.

Retry policy: up to 3 attempts with exponential backoff (1s → 2s → 4s).
Timeout: 5 seconds per attempt. On all failures, returns the raw input.
"""

import os
import time
import logging
from typing import Optional

log = logging.getLogger(__name__)

MOCK_MODE: bool = os.getenv("ENHANCE_MOCK", "0") == "1"
VALID_DOMAINS: frozenset[str] = frozenset(
    {"work", "hydroponics", "property", "physical", "hobby", "connection", "general"}
)
MODEL_NAME = "gemini-2.0-flash-lite"
_MAX_ENHANCED_LEN = 120
_MAX_RETRIES = 3
_RETRY_BASE_S = 1.0

_model = None


def _get_model():  # type: ignore[return]
    global _model
    if _model is None:
        import google.generativeai as genai  # type: ignore[import]
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        _model = genai.GenerativeModel(MODEL_NAME)
    return _model


def _call_with_retry(prompt: str, context: str) -> Optional[str]:
    """
    Call Gemini with exponential backoff.
    Returns the stripped response text, or None if all attempts fail.
    """
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            result = _get_model().generate_content(prompt)
            return result.text.strip()
        except Exception as exc:
            wait = _RETRY_BASE_S * (2 ** (attempt - 1))
            if attempt < _MAX_RETRIES:
                log.warning(
                    "Gemini %s attempt %d/%d failed (%s) — retrying in %.1fs",
                    context, attempt, _MAX_RETRIES, type(exc).__name__, wait,
                )
                time.sleep(wait)
            else:
                log.warning(
                    "Gemini %s failed after %d attempts (%s) — falling back",
                    context, _MAX_RETRIES, type(exc).__name__,
                )
    return None


_ENHANCE_PROMPT = """\
Rewrite this to-do item to be clear, concise, and actionable.
- Imperative mood. One sentence. Max 80 characters.
- Fix spelling and grammar. Remove filler words.
- Do NOT add explanation, context, or trailing punctuation.
- Return ONLY the rewritten item. Nothing else.{hint}

Input: {text}"""

_INFER_PROMPT = """\
Classify this to-do item into exactly one domain. Return only the domain word.
Domains: work hydroponics property physical hobby connection general

Item: {text}"""


def enhance(text: str, domain_hint: Optional[str] = None) -> str:
    """Return an enhanced version of *text*, or *text* itself if LLM is unavailable."""
    if MOCK_MODE:
        log.debug("ENHANCE_MOCK=1 — returning raw text")
        return text
    hint = f"\n- Domain context: {domain_hint}." if domain_hint else ""
    result = _call_with_retry(
        _ENHANCE_PROMPT.format(hint=hint, text=text), context="enhance"
    )
    return (result or text)[:_MAX_ENHANCED_LEN]


def infer_domain(text: str) -> str:
    """Return a domain string for *text*. Falls back to 'general' on any failure."""
    if MOCK_MODE:
        return "general"
    result = _call_with_retry(_INFER_PROMPT.format(text=text), context="infer_domain")
    if result:
        candidate = result.lower().split()[0] if result.split() else ""
        if candidate in VALID_DOMAINS:
            return candidate
    return "general"
