from flask import Flask


def create_app():
    app = Flask(__name__)

    from .routes.sms import sms_bp
    from .routes.jeannie import jeannie_bp
    app.register_blueprint(sms_bp)
    app.register_blueprint(jeannie_bp)

    return app
