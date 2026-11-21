from pathlib import Path

import click
from flask import Flask, request
from flask_login import LoginManager
from flask_wtf.csrf import CSRFError, CSRFProtect

from config import Config
from app.models import db, User

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Sign in to open your dashboard."
csrf = CSRFProtect()


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config is not None:
        app.config.update(test_config)
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("Set SECRET_KEY in the environment or project .env file.")

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)

    login_manager.init_app(app)
    csrf.init_app(app)

    from app.auth import auth, handle_csrf_error
    from app.routes import main

    app.register_blueprint(auth)
    app.register_blueprint(main)
    app.register_error_handler(CSRFError, handle_csrf_error)

    @app.after_request
    def protect_session_pages(response):
        # These pages contain a CSRF token or account-specific information.
        if request.blueprint in {"auth", "main"}:
            response.cache_control.no_store = True
        return response

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
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
