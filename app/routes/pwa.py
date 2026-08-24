"""routes/pwa.py — The Burrow PWA routes."""
import re
import logging
from flask import Blueprint, render_template, request, jsonify, current_app

from ..parser import parse, ParseResult
from ..enhancer import enhance, infer_domain
from ..vault import write_ticket, write_index, vault_root
from ..ack import random_ack
from ..preferences import get_prefs, save_prefs
from ..quick_actions import get_actions

log = logging.getLogger(__name__)
pwa_bp = Blueprint("pwa", __name__)


# ── helpers ───────────────────────────────────────────────────────────────────

def _queue_tickets(limit: int = 20) -> list[dict]:
    index_path = vault_root() / "00_Queue" / "Index.md"
    if not index_path.exists():
        return []
    content = index_path.read_text(encoding="utf-8")
    body = re.sub(r"^---[\s\S]*?---\n?", "", content)
    body = re.sub(r"%%[\s\S]*?%%\n?", "", body)
    links = re.findall(r"\[\[([^\]]+)\]\]", body)
    ticket_dir = vault_root() / "00_Queue" / "Tickets"
    tickets = []
    for link in links[:limit]:
        tp = ticket_dir / f"{link}.md"
        if not tp.exists():
            continue
        meta = {}
        fm = re.match(r"^---\n([\s\S]*?)\n---", tp.read_text(encoding="utf-8"))
        if fm:
            for line in fm.group(1).splitlines():
                if ": " in line:
                    k, v = line.split(": ", 1)
                    meta[k.strip()] = v.strip()
        tickets.append({
            "id":       link,
            "title":    meta.get("title", link),
            "domain":   meta.get("domain", ""),
            "priority": meta.get("priority", "normal"),
            "est_min":  meta.get("est_min", "30"),
            "status":   meta.get("status", "queued"),
        })
    return tickets


def _write(title: str, domain: str, priority: str, est_min: int = 30) -> tuple[str, str]:
    """write ticket + index, return (ticket_id, ack)."""
    tid = write_ticket(title, domain, priority, est_min)
    write_index(tid, priority)
    return tid, random_ack()


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
        return ({"error": "body required"}, 400)
    try:
        parsed   = parse(body)
        enhanced = enhance(parsed.raw_text, parsed.domain)
        domain   = parsed.domain or infer_domain(enhanced)
        tid, ack = _write(enhanced, domain, parsed.priority, parsed.est_min)
        return jsonify({"ack": ack, "ticket_id": tid, "enhanced": enhanced})
    except Exception as e:
        log.error("add_task: %s", e, exc_info=True)
        return ({"error": str(e)}, 500)


@pwa_bp.route("/api/quick-action", methods=["POST"])
def quick_action():
    data      = request.get_json(force=True) or {}
    action_id = data.get("action_id", "")
    user      = data.get("user", "John")
    priority  = data.get("priority", "normal")

    actions = get_actions()
    action  = next((a for a in actions if a["id"] == action_id), None)
    if not action:
        return ({"error": "unknown action"}, 400)

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

        # freeform
        body = data.get("body", "").strip()
        if not body:
            return ({"error": "body required"}, 400)
        parsed   = parse(body)
        enhanced = enhance(parsed.raw_text, parsed.domain)
        domain   = parsed.domain or (action.get("domain")) or infer_domain(enhanced)
        tid, ack = _write(enhanced, domain, priority, parsed.est_min)
        return jsonify({"ack": ack, "ticket_id": tid, "enhanced": enhanced})

    except Exception as e:
        log.error("quick_action: %s", e, exc_info=True)
        return ({"error": str(e)}, 500)


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
