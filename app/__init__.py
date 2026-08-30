import os
import pathlib
import logging
from flask import Flask, Response

log = logging.getLogger(__name__)

# Security headers added to every response
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    # CSP: allow inline styles/scripts (Alpine.js + Tailwind CDN), same-origin assets
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.tailwindcss.com https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "font-src 'self' data: https://fonts.gstatic.com; "
        "frame-ancestors 'none';"
    ),
}


def create_app() -> Flask:
    root = pathlib.Path(__file__).parent.parent  # pensieve-sms/
    app = Flask(
        __name__,
        template_folder=str(root / "templates"),
        static_folder=str(root / "static"),
    )

    # ── blueprints ────────────────────────────────────────────────────────────
    from .routes.sms import sms_bp
    from .routes.jeannie import jeannie_bp
    from .routes.pwa import pwa_bp
    from .routes.health import health_bp
    app.register_blueprint(sms_bp)
    app.register_blueprint(jeannie_bp)
    app.register_blueprint(pwa_bp)
    app.register_blueprint(health_bp)

    # ── security headers ──────────────────────────────────────────────────────
    @app.after_request
    def add_security_headers(response: Response) -> Response:
        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response

    # ── DB teardown ───────────────────────────────────────────────────────────
    @app.teardown_appcontext
    def close_db(_exc: BaseException | None = None) -> None:
        """Close the thread-local SQLite connection at end of each request."""
        try:
            from . import database
            database.close_conn()
        except Exception:
            pass

    # ── startup: init DB + validate environment ───────────────────────────────
    with app.app_context():
        try:
            from . import database
            database.init_db()
        except Exception as exc:
            log.warning("DB init skipped — VAULT_ROOT may not be set: %s", exc)

        vault = os.environ.get("VAULT_ROOT", "")
        if not vault:
            log.warning(
                "VAULT_ROOT is not set. Ticket writes will fail. "
                "Set VAULT_ROOT in /etc/pensieve.env and restart."
            )
        elif not pathlib.Path(vault, "00_Queue", "Index.md").exists():
            log.warning(
                "VAULT_ROOT=%s exists but 00_Queue/Index.md is missing. "
                "Run the installer or create it manually.", vault
            )

    return app
