"""
enhancer.py - Gemini Flash Lite enhancement + domain inference.

Set ENHANCE_MOCK=1 to bypass LLM (returns raw text). Use for local dev without API key.
"""

import os
import logging
from typing import Optional

log = logging.getLogger(__name__)
MOCK_MODE = os.getenv("ENHANCE_MOCK", "0") == "1"
VALID_DOMAINS = {"work", "hydroponics", "property", "physical", "hobby", "connection", "general"}

_model = None


def _get_model():
    global _model
    if _model is None:
        import google.generativeai as genai
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        _model = genai.GenerativeModel("gemini-2.0-flash-lite")
    return _model


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
    if MOCK_MODE:
        log.info("ENHANCE_MOCK=1 - returning raw text")
        return text
    hint = f"\n- Domain context: {domain_hint}." if domain_hint else ""
    try:
        return _get_model().generate_content(
            _ENHANCE_PROMPT.format(hint=hint, text=text)
        ).text.strip()[:120]
    except Exception as e:
        log.warning("enhance() failed: %s - returning raw text", e)
        return text


def infer_domain(text: str) -> str:
    if MOCK_MODE:
        return "general"
    try:
        result = _get_model().generate_content(
            _INFER_PROMPT.format(text=text)
        ).text.strip().lower()
        return result if result in VALID_DOMAINS else "general"
    except Exception as e:
        log.warning("infer_domain() failed: %s - returning 'general'", e)
        return "general"
