from pathlib import Path

import click
from flask import Flask, request
from flask_login import LoginManager
from flask_wtf.csrf import CSRFError, CSRFProtect

from config import Config
from app.models import db, User
from app.session_security import validate_request_session

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Sign in to open your dashboard."
csrf = CSRFProtect()


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config is not None:
        app.config.update(test_config)
    if not app.secret_key or app.secret_key == "replace-with-a-random-secret":
        raise RuntimeError("Set SECRET_KEY in the environment or project .env file.")

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)

    login_manager.init_app(app)
    app.before_request(validate_request_session)
    csrf.init_app(app)

    from app.accounts import accounts
    from app.activity import activity
    from app.auth import auth, handle_csrf_error
    from app.records import records
    from app.routes import access_restricted, main

    app.register_blueprint(auth)
    app.register_blueprint(main)
    app.register_blueprint(records)
    app.register_blueprint(accounts)
    app.register_blueprint(activity)
    app.register_error_handler(CSRFError, handle_csrf_error)
    app.register_error_handler(403, access_restricted)

    @app.after_request
    def protect_response(response):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'none'; object-src 'none'; "
            "frame-ancestors 'none'; form-action 'self'"
        )
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Flask-WTF checks the same-origin Referer on secure form submissions.
        response.headers["Referrer-Policy"] = "same-origin"
        # These pages contain a CSRF token or account-specific information.
        if request.blueprint in {"auth", "main", "records", "accounts", "activity"}:
            response.cache_control.no_store = True
        return response

    @login_manager.user_loader
    def load_user(user_id):
        try:
            identity = int(user_id)
            if 0 < identity <= 2**63 - 1:
                return db.session.get(User, identity)
        except (TypeError, ValueError):
            return None

    @app.cli.command("init-db")
    def init_db():
        """Create missing database tables without deleting existing data."""
        db.create_all()
        click.echo("Database tables initialized.")

    from app.seed import register_seed_command
    register_seed_command(app)

    return app
