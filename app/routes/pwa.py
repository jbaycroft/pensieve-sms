"""routes/pwa.py — The Burrow PWA routes."""
import re
import logging
from flask import Blueprint, render_template, request, jsonify, current_app

from ..parser import parse
from ..enhancer import enhance, infer_domain
from ..vault import write_ticket, write_index
from ..ack import random_ack
from ..preferences import get_prefs, save_prefs
from ..quick_actions import get_actions

log = logging.getLogger(__name__)
pwa_bp = Blueprint("pwa", __name__)

_MAX_BODY_LEN = 500
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


# ── helpers ───────────────────────────────────────────────────────────────────

def _queue_tickets(limit: int = 20) -> list[dict]:
    """Return ordered queue from SQLite. Fast O(1) join, no file I/O."""
    from ..database import get_queue
    return get_queue(limit)


def _write(title: str, domain: str, priority: str, est_min: int = 30) -> tuple[str, str]:
    """Write ticket + queue entry, return (ticket_id, ack)."""
    tid = write_ticket(title, domain, priority, est_min)
    write_index(tid, priority)
    return tid, random_ack()


def _parse_and_write(body: str, priority_override: str = "") -> dict:
    """Full parse → enhance → write pipeline. Returns jsonify-ready dict.

    priority_override: if non-empty, overrides the parsed priority prefix.
    Otherwise the prefix in the body text controls priority (!! → urgent, ! → high).
    """
    parsed   = parse(body)
    enhanced = enhance(parsed.raw_text, parsed.domain)
    domain   = parsed.domain or infer_domain(enhanced)
    priority = priority_override if priority_override else parsed.priority
    tid, ack = _write(enhanced, domain, priority, parsed.est_min)
    return {"ack": ack, "ticket_id": tid, "enhanced": enhanced}


# ── pages ─────────────────────────────────────────────────────────────────────

@pwa_bp.route("/")
def home():
    return render_template("home.html", actions=get_actions())


# ── partials (HTMX) ───────────────────────────────────────────────────────────

@pwa_bp.route("/api/queue")
def queue():
    return render_template("partials/queue.html", tickets=_queue_tickets())


@pwa_bp.route("/api/action-panel/<action_id>")
def action_panel(action_id: str):
    actions = get_actions()
    action = next((a for a in actions if a["id"] == action_id), None)
    if not action:
        return ("Not found", 404)
    user = request.args.get("user", "John")
    prefs = get_prefs(user, action_id) if action.get("type") == "coffee" else {}
    # Ensure coffee prefs have defaults
    if action.get("type") == "coffee":
        prefs = {"size": "medium", "drink": "drip", "notes": "", **prefs}
    return render_template("partials/action_panel.html", action=action, user=user, prefs=prefs)


# ── api ───────────────────────────────────────────────────────────────────────

@pwa_bp.route("/api/task", methods=["POST"])
def add_task():
    data   = request.get_json(force=True) or {}
    body   = data.get("body", "").strip()
    if not body:
        return jsonify({"error": "body required"}), 400
    if len(body) > _MAX_BODY_LEN:
        return jsonify({"error": f"body exceeds {_MAX_BODY_LEN} character limit"}), 400
    try:
        return jsonify(_parse_and_write(body))
    except Exception as e:
        log.error("add_task: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500


@pwa_bp.route("/api/quick-action", methods=["POST"])
def quick_action():
    data      = request.get_json(force=True) or {}
    action_id = data.get("action_id", "")
    user      = data.get("user", "John")
    priority  = data.get("priority", "normal")

    # Input validation
    if not _SAFE_ID.match(action_id):
        return jsonify({"error": "invalid action_id"}), 400
    if not _SAFE_ID.match(user):
        return jsonify({"error": "invalid user"}), 400

    actions = get_actions()
    action  = next((a for a in actions if a["id"] == action_id), None)
    if not action:
        return jsonify({"error": "unknown action"}), 400

    try:
        if action["type"] == "coffee":
            size  = data.get("size", "medium")
            drink = data.get("drink", "drip")
            notes = data.get("notes", "")
            if data.get("remember"):
                save_prefs(user, action_id, {"size": size, "drink": drink, "notes": notes})
            title = f"{user}'s {size} {drink}" + (f" — {notes}" if notes else "")
            tid, ack = _write(title, "connection", priority, 5)
            return jsonify({"ack": ack, "ticket_id": tid, "enhanced": title})

        if action["type"] == "prefilled":
            title    = action.get("task", action["label"])
            est_min  = int(action.get("est_min", 30))
            domain   = action.get("domain") or "general"
            tid, ack = _write(title, domain, priority, est_min)
            return jsonify({"ack": ack, "ticket_id": tid, "enhanced": title})

        # freeform — use shared _parse_and_write helper
        body = data.get("body", "").strip()
        if not body:
            return jsonify({"error": "body required"}), 400
        if len(body) > _MAX_BODY_LEN:
            return jsonify({"error": f"body exceeds {_MAX_BODY_LEN} character limit"}), 400
        result = _parse_and_write(body, priority_override=priority)
        return jsonify(result)

    except Exception as e:
        log.error("quick_action: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500


@pwa_bp.route("/api/preferences/<user>/<action>", methods=["GET"])
def get_preferences(user: str, action: str):
    return jsonify(get_prefs(user, action))


@pwa_bp.route("/api/preferences/<user>/<action>", methods=["POST"])
def set_preferences(user: str, action: str):
    save_prefs(user, action, request.get_json(force=True) or {})
    return jsonify({"ok": True})


@pwa_bp.route("/manifest.json")
def manifest():
    return jsonify({
        "name":             "The Burrow",
        "short_name":       "Burrow",
        "start_url":        "/",
        "display":          "standalone",
        "background_color": "#0f0f1a",
        "theme_color":      "#9b1d20",
        "icons": [
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    })


@pwa_bp.route("/sw.js")
def service_worker():
    return current_app.send_static_file("sw.js")
