"""Shared rendering and transaction helpers for the signed-in workspace."""

from flask import render_template
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from app.forms import LogoutForm
from app.models import db


def render_workspace(template, *, status=200, **context):
    return render_template(template, logout_form=LogoutForm(), **context), status


def reserve_write():
    """Serialize SQLite writers before rechecking permissions and invariants."""
    db.session.execute(text("BEGIN IMMEDIATE"))


def save_changes(change):
    """Reserve the writer, run guarded work, and return a safe form error on failure."""
    try:
        reserve_write()
        change()
        db.session.commit()
    except ValueError as error:
        db.session.rollback()
        return str(error), 400
    except IntegrityError:
        db.session.rollback()
        return "The change conflicts with existing data. Check the values and try again.", 409
    except OperationalError:
        db.session.rollback()
        return "The database could not save the change. Please try again.", 503
    except SQLAlchemyError:
        db.session.rollback()
        return "The database could not save the change.", 500
    return None, None
