"""notify.py — Push notifications via ntfy.sh.

Fires a background HTTP POST to ntfy.sh whenever a task is created.
Completely non-blocking — failures are logged but never affect the
request that triggered the notification.

Configuration (via environment):
    NTFY_TOPIC       Topic name (default: theburrow-tasks)
    NTFY_SERVER      Server URL (default: https://ntfy.sh)
    NTFY_ENABLED     Set to "0" to disable (default: "1")
"""

from __future__ import annotations

import logging
import os
import threading
import urllib.request
import urllib.error

log = logging.getLogger(__name__)

NTFY_TOPIC: str = os.getenv("NTFY_TOPIC", "theburrow-tasks")
NTFY_SERVER: str = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
NTFY_ENABLED: bool = os.getenv("NTFY_ENABLED", "1") != "0"


def notify(title: str, body: str, *, tags: str = "scroll", priority: str = "default") -> None:
    """Send a push notification via ntfy.sh. Non-blocking (runs in a thread).

    Args:
        title:    Notification title (e.g. "New quest from Jeannie").
        body:     Notification body (e.g. the task description).
        tags:     Comma-separated emoji shortcodes for ntfy.
        priority: ntfy priority: min, low, default, high, urgent.
    """
    if not NTFY_ENABLED:
        return

    def _send() -> None:
        url = f"{NTFY_SERVER}/{NTFY_TOPIC}"
        try:
            req = urllib.request.Request(
                url,
                data=body.encode("utf-8"),
                headers={
                    "Title": title,
                    "Tags": tags,
                    "Priority": priority,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5):
                pass
            log.debug("ntfy sent: %s", title)
        except Exception as exc:
            log.warning("ntfy failed: %s", exc)

    threading.Thread(target=_send, daemon=True).start()
