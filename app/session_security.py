"""Bind Flask-Login sessions to the current credential and a fixed deadline."""

from hmac import compare_digest, digest
from time import time

from flask import current_app, request, session
from flask_login import current_user, logout_user

from app.models import User, db


def credential_tag(user_id, password_hash):
    # The signed cookie carries a keyed tag, never the stored password hash.
    key = current_app.secret_key
    if isinstance(key, str):
        key = key.encode()
    message = f"securerole-session-v1:{user_id}:{password_hash}".encode()
    return digest(key, message, "sha256").hex()


def bind_session(user):
    session["credential_tag"] = credential_tag(user.id, user.password_hash)
    session["auth_deadline"] = int(time()) + int(current_app.permanent_session_lifetime.total_seconds())


def validate_session(*, refresh=False):
    """Clear expired or revoked sessions before authorization reads the actor."""
    if "_user_id" not in session:
        return
    user = current_user
    deadline = session.get("auth_deadline")
    tag = session.get("credential_tag")
    valid = (user.is_authenticated and type(deadline) is int and time() < deadline
             and isinstance(tag, str) and tag.isascii())
    if valid:
        password_hash = user.password_hash
        if refresh:
            # A reset may have committed after the request initially loaded the user.
            password_hash = db.session.scalar(db.select(User.password_hash).where(User.id == user.id))
        valid = password_hash is not None and compare_digest(tag, credential_tag(user.id, password_hash))
    if not valid:
        session.clear()
        logout_user()


def validate_request_session():
    if request.endpoint is not None and request.endpoint != "static":
        validate_session()
