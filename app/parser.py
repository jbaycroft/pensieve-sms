"""
parser.py - SMS message prefix parser.

Parse order (left-to-right):
  1. Priority prefix:  !! (urgent) | ! (high) | (none -> normal)
  2. Time prefix:      N:  e.g. 5: or 30:
  3. Domain prefix:    w: h: p: f: ho: c: (and long forms)
  4. Raw text body
"""

import re
from dataclasses import dataclass
from typing import Optional

DOMAIN_MAP: dict[str, str] = {
    "w": "work",        "work": "work",
    "h": "hydroponics", "hydro": "hydroponics",
    "p": "property",    "prop": "property",
    "f": "physical",    "fit": "physical",
    "ho": "hobby",      "hobby": "hobby",
    "c": "connection",  "connect": "connection",
}


@dataclass
class ParseResult:
    priority: str          # "urgent" | "high" | "normal"
    est_min: int           # minutes, default 30
    domain: Optional[str]  # None = needs LLM inference
    raw_text: str          # body after all prefixes stripped


def parse(body: str) -> ParseResult:
    text = body.strip()

    # 1. Priority
    priority = "normal"
    if text.startswith("!!"):
        priority, text = "urgent", text[2:].strip()
    elif text.startswith("!"):
        priority, text = "high", text[1:].strip()

    # 2. Time prefix (pure digits followed by colon)
    est_min = 30
    m = re.match(r"^(\d+):\s*(.+)$", text, re.DOTALL)
    if m:
        est_min = max(1, int(m.group(1)))
        text = m.group(2).strip()

    # 3. Domain prefix (word followed by colon)
    domain: Optional[str] = None
    m = re.match(r"^(\w+):\s*(.+)$", text, re.DOTALL)
    if m and m.group(1).lower() in DOMAIN_MAP:
        domain = DOMAIN_MAP[m.group(1).lower()]
        text = m.group(2).strip()

    return ParseResult(priority=priority, est_min=est_min, domain=domain, raw_text=text)
