import pathlib
import logging
from flask import Flask

log = logging.getLogger(__name__)


def create_app():
    root = pathlib.Path(__file__).parent.parent  # pensieve-sms/
    app = Flask(
        __name__,
        template_folder=str(root / "templates"),
        static_folder=str(root / "static"),
    )

    from .routes.sms import sms_bp
    from .routes.jeannie import jeannie_bp
    from .routes.pwa import pwa_bp
    app.register_blueprint(sms_bp)
    app.register_blueprint(jeannie_bp)
    app.register_blueprint(pwa_bp)

    # Initialise SQLite schema on startup (idempotent)
    with app.app_context():
        try:
            from . import database
            database.init_db()
        except Exception as e:
            log.warning("DB init skipped (VAULT_ROOT not set?): %s", e)

    return app
