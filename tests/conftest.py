import pytest

from app import create_app
from app.migrations import migrate_database
from app.models import db


@pytest.fixture
def app(tmp_path):
    application = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-only-secret",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
    })
    with application.app_context():
        migrate_database()
        yield application
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def seeded(app):
    result = app.test_cli_runner().invoke(args=["seed-db"])
    assert result.exit_code == 0, result.output
    return app
