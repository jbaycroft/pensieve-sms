"""
enhancer.py — LLM enhancement and domain inference.

Supports two backends, selected by the LLM_BACKEND environment variable:

  LLM_BACKEND=gemini   (default) — Gemini Flash Lite via Google Generative AI SDK.
                                    Requires GEMINI_API_KEY.
  LLM_BACKEND=ollama              — Local Ollama server (no internet required).
                                    Requires Ollama running at OLLAMA_BASE_URL
                                    with OLLAMA_MODEL pulled.

Resilience
----------
- Each backend retries up to _MAX_RETRIES times with exponential backoff.
- If the primary backend fails completely AND the other backend is available,
  a one-shot fallback attempt is made before returning the raw input.
- ENHANCE_MOCK=1 bypasses all LLM calls entirely (development / testing).

Environment variables
---------------------
LLM_BACKEND       gemini | ollama         (default: gemini)
GEMINI_API_KEY    required when backend=gemini
OLLAMA_BASE_URL   Ollama API root         (default: http://localhost:11434)
OLLAMA_MODEL      model tag to use        (default: qwen2.5:1.5b)
OLLAMA_TIMEOUT    per-request timeout s   (default: 15)
ENHANCE_MOCK      1 to skip all LLM calls (default: 0)
"""

from __future__ import annotations

import json
import os
import time
import logging
import urllib.request
import urllib.error
from typing import Optional

log = logging.getLogger(__name__)

# ── runtime configuration ─────────────────────────────────────────────────────

MOCK_MODE: bool = os.getenv("ENHANCE_MOCK", "0") == "1"

LLM_BACKEND: str = os.getenv("LLM_BACKEND", "gemini").lower()
assert LLM_BACKEND in ("gemini", "ollama"), (
    f"LLM_BACKEND must be 'gemini' or 'ollama', got {LLM_BACKEND!r}"
)

# Gemini
GEMINI_MODEL_NAME: str = "gemini-2.0-flash-lite"

# Ollama
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "phi3")
OLLAMA_TIMEOUT: int = int(os.getenv("OLLAMA_TIMEOUT", "15"))

VALID_DOMAINS: frozenset[str] = frozenset(
    {"work", "hydroponics", "property", "physical", "hobby", "connection", "general"}
)
_MAX_ENHANCED_LEN: int = 120
_MAX_RETRIES: int = 2
_RETRY_BASE_S: float = 0.3

# Track backend failures within a process lifetime so we don't waste
# 13 seconds of retry loops when both backends are known-dead.
_backend_dead: dict[str, float] = {}  # name → timestamp when marked dead
_DEAD_TTL_S: float = 120.0  # retry a dead backend after 2 minutes


def _mark_dead(name: str) -> None:
    """Mark a backend as dead so subsequent calls skip it instantly."""
    _backend_dead[name] = time.monotonic()
    log.info("Marked %s backend as dead for %.0fs", name, _DEAD_TTL_S)


def _is_dead(name: str) -> bool:
    """Return True if the backend was recently marked dead."""
    ts = _backend_dead.get(name)
    if ts is None:
        return False
    if time.monotonic() - ts > _DEAD_TTL_S:
        del _backend_dead[name]
        log.info("Backend %s dead-TTL expired, will retry", name)
        return False
    return True


# ── Gemini backend ────────────────────────────────────────────────────────────

_gemini_model = None


def _get_gemini_model():  # type: ignore[return]
    global _gemini_model
    if _gemini_model is None:
        import google.generativeai as genai  # type: ignore[import]
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        genai.configure(api_key=api_key)
        _gemini_model = genai.GenerativeModel(GEMINI_MODEL_NAME)
    return _gemini_model


def _call_gemini(prompt: str, context: str) -> Optional[str]:
    """Call Gemini with exponential backoff. Returns response text or None."""
    if _is_dead("gemini"):
        return None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            result = _get_gemini_model().generate_content(prompt)
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
                    "Gemini %s exhausted after %d attempts (%s)",
                    context, _MAX_RETRIES, type(exc).__name__,
                )
                _mark_dead("gemini")
    return None


# ── Ollama backend ────────────────────────────────────────────────────────────

def _check_ollama_available() -> bool:
    """Return True if the Ollama server is reachable. Does not raise."""
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3):
            return True
    except Exception:
        return False


def _call_ollama(prompt: str, context: str) -> Optional[str]:
    """
    Call the local Ollama REST API with exponential backoff.

    Uses /api/generate with stream=False for a single synchronous response.
    Returns the response text or None if all attempts fail.
    """
    if _is_dead("ollama"):
        return None
    url = f"{OLLAMA_BASE_URL}/api/generate"
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 150,
        },
    }).encode("utf-8")

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
                data = json.load(resp)
                text = data.get("response", "").strip()
                if text:
                    return text
                raise ValueError("Empty response from Ollama")
        except Exception as exc:
            wait = _RETRY_BASE_S * (2 ** (attempt - 1))
            if attempt < _MAX_RETRIES:
                log.warning(
                    "Ollama %s attempt %d/%d failed (%s) — retrying in %.1fs",
                    context, attempt, _MAX_RETRIES, type(exc).__name__, wait,
                )
                time.sleep(wait)
            else:
                log.warning(
                    "Ollama %s exhausted after %d attempts (%s)",
                    context, _MAX_RETRIES, type(exc).__name__,
                )
                _mark_dead("ollama")
    return None


# ── unified dispatch ──────────────────────────────────────────────────────────

def _call_llm(prompt: str, context: str) -> Optional[str]:
    """
    Dispatch to the configured backend. If the primary backend fails completely,
    attempt one call on the secondary backend before returning None.
    """
    if LLM_BACKEND == "ollama":
        result = _call_ollama(prompt, context)
        if result is None:
            log.warning("Ollama unavailable for %s — attempting Gemini fallback", context)
            result = _call_gemini(prompt, context)
    else:
        result = _call_gemini(prompt, context)
        if result is None:
            log.warning("Gemini unavailable for %s — attempting Ollama fallback", context)
            result = _call_ollama(prompt, context)

    return result


# ── prompts ───────────────────────────────────────────────────────────────────

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


# ── public API ────────────────────────────────────────────────────────────────

def enhance(text: str, domain_hint: Optional[str] = None) -> str:
    """
    Return an LLM-enhanced version of *text*.
    Falls back to *text* itself if both backends are unavailable.
    """
    if MOCK_MODE:
        log.debug("ENHANCE_MOCK=1 — returning raw text")
        return text
    hint = f"\n- Domain context: {domain_hint}." if domain_hint else ""
    result = _call_llm(_ENHANCE_PROMPT.format(hint=hint, text=text), context="enhance")
    return (result or text)[:_MAX_ENHANCED_LEN]


def infer_domain(text: str) -> str:
    """
    Return a domain label for *text*.
    Falls back to 'general' if both backends are unavailable.
    """
    if MOCK_MODE:
        return "general"
    result = _call_llm(_INFER_PROMPT.format(text=text), context="infer_domain")
    if result:
        candidate = result.lower().split()[0] if result.split() else ""
        if candidate in VALID_DOMAINS:
            return candidate
    return "general"
