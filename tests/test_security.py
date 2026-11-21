"""Regression tests for Phase 7 session, response and validation controls."""

from urllib.parse import urlsplit

import pytest
from sqlalchemy.orm import Session

from app import create_app
from app import workspace
from app.models import AccessLog, User, db
from app.rbac import Action
from tests.test_features import PASSWORD, account_fields, demo, sign_in, submit, token


def test_password_reset_revokes_prior_sessions(demo):
    app, ids = demo
    clients = [sign_in(app, "dahlia"), sign_in(app, "dahlia")]
    assert all(client.get("/dashboard/student").status_code == 200 for client in clients)
    with app.app_context():
        stored_hash = db.session.get(User, ids["dahlia"]).password_hash
    with clients[0].session_transaction() as cookie:
        assert cookie.get("credential_tag") and stored_hash not in cookie.values()
        assert PASSWORD not in cookie.values()

    admin = sign_in(app, "atlas")
    replacement = "fictional-password-after-reset"
    response = submit(admin, f"/users/{ids['dahlia']}/password", password=replacement)
    assert response.status_code == 303
    for client in clients:
        rejected = client.get("/dashboard/student")
        assert rejected.status_code == 302 and urlsplit(rejected.location).path == "/login"
        with client.session_transaction() as cookie:
            assert "_user_id" not in cookie
    assert submit(app.test_client(), "/login", username="dahlia", password=PASSWORD).status_code == 401
    assert sign_in(app, "dahlia", replacement).get("/dashboard/student").status_code == 200

    with app.app_context():
        logged = db.session.scalars(db.select(AccessLog).where(AccessLog.action == Action.MANAGE_USERS)).all()
        assert len(logged) == 2
        assert all(log.actor_user_id == ids["atlas"] and log.resource == "users" for log in logged)
        assert all(replacement not in (log.action, log.resource, log.decision) for log in logged)


def test_session_deadline_is_absolute(demo, monkeypatch):
    app, _ = demo
    now = 1_000_000
    monkeypatch.setattr("app.session_security.time", lambda: now)
    client = sign_in(app, "dahlia")
    with client.session_transaction() as cookie:
        deadline = cookie["auth_deadline"]
        assert deadline == now + 8 * 60 * 60
    now = deadline - 1
    assert client.get("/dashboard/student").status_code == 200
    now = deadline
    assert urlsplit(client.get("/dashboard/student").location).path == "/login"


def test_reset_during_request_blocks_mutation(demo, monkeypatch):
    app, ids = demo
    client = sign_in(app, "birch")
    csrf = token(client.get("/dashboard/teacher"))
    reserve_write = workspace.reserve_write

    def reset_then_reserve():
        with Session(db.engine) as session, session.begin():
            session.get(User, ids["birch"]).set_password("fictional-concurrent-reset")
        reserve_write()

    monkeypatch.setattr(workspace, "reserve_write", reset_then_reserve)
    response = client.post(f"/students/{ids['elm']}/record/new", data={
        "csrf_token": csrf, "course": "Concurrent request", "marks": "50",
    })
    assert response.status_code == 302 and urlsplit(response.location).path == "/login"
    with app.app_context():
        assert db.session.get(User, ids["elm"]).student_record is None
        entry = db.session.scalar(db.select(AccessLog).filter_by(action=Action.CREATE_RECORD))
        assert entry.decision == "Denied" and entry.actor_user_id is None


def test_session_without_credential_binding_requires_sign_in(demo):
    app, ids = demo
    client = app.test_client()
    with client.session_transaction() as cookie:
        cookie["_user_id"] = str(ids["dahlia"])
    assert urlsplit(client.get("/dashboard/student").location).path == "/login"


def test_headers_and_request_limit(demo):
    app, _ = demo
    client = app.test_client()
    response = client.get("/login")
    headers = response.headers
    assert "default-src 'self'" in headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert "form-action 'self'" in headers["Content-Security-Policy"]
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "same-origin"
    assert "no-store" in headers["Cache-Control"]
    assert client.post("/login", data={"username": "a" * 65536}).status_code == 413


def test_configured_trusted_hosts(demo):
    app, _ = demo
    app.config["TRUSTED_HOSTS"] = ["localhost"]
    client = app.test_client()
    assert client.get("/login", base_url="http://localhost").status_code == 200
    assert client.get("/login", base_url="http://other.test").status_code == 400


def test_example_key_is_rejected():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app({"SECRET_KEY": "replace-with-a-random-secret"})


@pytest.mark.parametrize("updates", [
    {"username": "name\twith-tab"},
    {"email": "person@incomplete"},
    {"display_name": "name\nwrapped"},
    {"password": " " * 16},
])
def test_rejects_invalid_account_input(demo, updates):
    app, ids = demo
    admin = sign_in(app, "atlas")
    fields = account_fields(ids)
    fields.update(password="fictional-initial-password")
    fields.update(updates)
    csrf = token(admin.get("/dashboard/admin"))
    response = admin.post("/users/new", data={"csrf_token": csrf, **fields})
    assert response.status_code == 400
    assert b'aria-invalid="true"' in response.data
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(User.id))) == 7
        assert db.session.scalar(db.select(AccessLog.id).filter_by(action=Action.MANAGE_USERS)) is None


def test_record_course_accepts_printable_unicode_and_marks_boundary(demo):
    app, ids = demo
    teacher = sign_in(app, "birch")
    path = f"/students/{ids['elm']}/record/new"
    csrf = token(teacher.get("/dashboard/teacher"))
    bad = teacher.post(path, data={"csrf_token": csrf, "course": "Two\nlines", "marks": "100"})
    assert bad.status_code == 400
    assert teacher.post(path, data={
        "csrf_token": csrf, "course": "Mathématiques théoriques", "marks": "100",
    }).status_code == 303
    with app.app_context():
        record = db.session.get(User, ids["elm"]).student_record
        assert (record.course, record.marks) == ("Mathématiques théoriques", 100)
