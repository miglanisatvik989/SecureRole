"""Server-side authentication sessions with opaque cookie tokens."""

from datetime import datetime, timezone
from hashlib import sha256
from hmac import compare_digest, digest
from secrets import token_urlsafe
from time import time

from flask import Blueprint, abort, current_app, flash, redirect, request, session, url_for
from flask_login import current_user, login_required, logout_user
from sqlalchemy import insert, select, update

from app.models import AuthSession, User, db

sessions = Blueprint("sessions", __name__)
TABLE = AuthSession.__table__


def credential_tag(user_id, password_hash):
    key = current_app.secret_key
    if isinstance(key, str):
        key = key.encode()
    message = f"securerole-session-v1:{user_id}:{password_hash}".encode()
    return digest(key, message, "sha256").hex()


def token_digest():
    token = session.get("session_token")
    if isinstance(token, str) and len(token) == 43 and token.isascii():
        return sha256(token.encode()).hexdigest()
    return None


def bind_session(user):
    """Create a session only if the verified credential still matches under the writer lock."""
    token = token_urlsafe(32)
    with db.engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        stored_hash = connection.scalar(select(User.password_hash).where(User.id == user.id))
        if stored_hash is None or not compare_digest(stored_hash, user.password_hash):
            return False
        now = int(time())
        deadline = now + int(current_app.permanent_session_lifetime.total_seconds())
        connection.execute(insert(TABLE).values(
            token_digest=sha256(token.encode()).hexdigest(), user_id=user.id,
            created_at=now, expires_at=deadline,
        ))
        connection.commit()
    session["session_token"] = token
    session["credential_tag"] = credential_tag(user.id, user.password_hash)
    session["auth_deadline"] = deadline
    return True


def clear_login():
    session.clear()
    logout_user()


def validate_session(*, refresh=False):
    """Clear expired or revoked sessions before authorization reads the actor."""
    if "_user_id" not in session:
        return
    user = current_user
    deadline = session.get("auth_deadline")
    tag = session.get("credential_tag")
    hashed_token = token_digest()
    now = time()
    valid = (user.is_authenticated and type(deadline) is int and now < deadline
             and isinstance(tag, str) and tag.isascii() and hashed_token is not None)
    if valid:
        policy = select(AuthSession.id).where(
            AuthSession.user_id == user.id, AuthSession.token_digest == hashed_token,
            AuthSession.expires_at == deadline, AuthSession.expires_at > now,
            AuthSession.revoked_at.is_(None),
        )
        valid = db.session.scalar(policy) is not None
    if valid:
        password_hash = user.password_hash
        if refresh:
            password_hash = db.session.scalar(select(User.password_hash).where(User.id == user.id))
        valid = password_hash is not None and compare_digest(tag, credential_tag(user.id, password_hash))
    if not valid:
        clear_login()


def validate_request_session():
    if request.endpoint is not None and request.endpoint != "static":
        validate_session()


def revoke(*, identity=None, all_sessions=False):
    """Revoke only sessions belonging to the signed-in account."""
    if identity is not None and not 0 < identity <= 2**63 - 1:
        abort(404)
    with db.engine.begin() as connection:
        now = int(time())
        conditions = [AuthSession.user_id == current_user.id, AuthSession.revoked_at.is_(None),
                      AuthSession.expires_at > now]
        if identity is not None:
            conditions.append(AuthSession.id == identity)
        elif not all_sessions:
            conditions.append(AuthSession.token_digest == token_digest())
        revoked = connection.execute(update(TABLE).where(*conditions).values(revoked_at=now)
                                     .returning(AuthSession.token_digest)).scalars().all()
    if identity is not None and not revoked:
        abort(404)
    return all_sessions or token_digest() in revoked


@sessions.get("/sessions")
@login_required
def index():
    from app.workspace import render_workspace

    rows = db.session.execute(select(AuthSession.id, AuthSession.created_at, AuthSession.expires_at,
                                    (AuthSession.token_digest == token_digest()).label("current"))
                              .where(AuthSession.user_id == current_user.id,
                                     AuthSession.revoked_at.is_(None), AuthSession.expires_at > int(time()))
                              .order_by(AuthSession.created_at.desc(), AuthSession.id.desc())).all()
    return render_workspace("sessions.html", rows=rows, active="sessions",
                            utc=lambda value: datetime.fromtimestamp(value, timezone.utc))


@sessions.post("/sessions/<int:identity>/revoke")
@login_required
def revoke_one(identity):
    if revoke(identity=identity):
        clear_login()
        return redirect(url_for("auth.login"), code=303)
    flash("Session signed out.", "success")
    return redirect(url_for("sessions.index"), code=303)


@sessions.post("/sessions/revoke-all")
@login_required
def revoke_all():
    revoke(all_sessions=True)
    clear_login()
    return redirect(url_for("auth.login"), code=303)
