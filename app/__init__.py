from pathlib import Path

import click
from flask import Flask
from flask_login import LoginManager

from config import Config
from app.models import db, User

login_manager = LoginManager()


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
