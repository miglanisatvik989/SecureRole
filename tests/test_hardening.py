"""Phase 7.1 defensive tests with temporary and fictional databases."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from hmac import new as hmac_new
import sqlite3

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.audit import commit_access_log
from app.audit_integrity import GENESIS, audit_key, entry_mac, inspect_audit, key_tag, verify_chain
from app.migrations import migrate_database
from app.models import AccessLog, AuthSession, LoginWindow, Role, StudentRecord, User, db
from tests.test_features import PASSWORD, account_fields, demo, sign_in, submit, token


def login_attempt(client, username, password="fictional-wrong-password"):
    return submit(client, "/login", username=username, password=password)


def test_account_throttle_expires_and_survives_restart(demo, monkeypatch):
    app, _ = demo
    app.config.update(LOGIN_ACCOUNT_LIMIT=2, LOGIN_SOURCE_LIMIT=10, LOGIN_WINDOW_SECONDS=30)
    now = 1000
    monkeypatch.setattr("app.login_limits.time", lambda: now)
    client = app.test_client()
    for _ in range(2):
        assert login_attempt(client, "dahlia").status_code == 401

    config = {name: app.config[name] for name in (
        "TESTING", "SECRET_KEY", "AUDIT_INTEGRITY_KEY", "SQLALCHEMY_DATABASE_URI",
        "LOGIN_ACCOUNT_LIMIT", "LOGIN_SOURCE_LIMIT", "LOGIN_WINDOW_SECONDS",
    )}
    restarted = create_app(config)
    client = restarted.test_client()
    blocked = login_attempt(client, "dahlia", PASSWORD)
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"] == "30"
    assert b"Too many sign-in attempts" in blocked.data and b"dahlia" not in blocked.data
    now = 1029
    assert login_attempt(client, "dahlia").headers["Retry-After"] == "1"
    now = 1030
    assert login_attempt(client, "dahlia", PASSWORD).status_code == 303
    with restarted.app_context():
        buckets = db.session.scalars(db.select(LoginWindow)).all()
        assert len(buckets) == 2 and all(row.attempts == 1 and row.expires_at == 1060 for row in buckets)
        assert all(len(row.bucket) == 64 and "dahlia" not in row.bucket for row in buckets)
        db.engine.dispose()


def test_source_throttle_covers_multiple_usernames(demo):
    app, _ = demo
    app.config.update(LOGIN_ACCOUNT_LIMIT=5, LOGIN_SOURCE_LIMIT=2)
    client = app.test_client()
    existing = login_attempt(client, "dahlia")
    unknown = login_attempt(client, "unknown-account")
    assert existing.status_code == unknown.status_code == 401
    assert b"Invalid username or password." in existing.data and b"Invalid username or password." in unknown.data
    assert login_attempt(client, "elm").status_code == 429


def test_concurrent_login_attempts_share_the_quota(demo):
    app, _ = demo
    app.config.update(LOGIN_ACCOUNT_LIMIT=2, LOGIN_SOURCE_LIMIT=10)

    def attempt(_):
        return login_attempt(app.test_client(), "fictional-account").status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sorted(pool.map(attempt, range(4))) == [401, 401, 429, 429]


def test_invalid_throttle_configuration_and_audit_key():
    with pytest.raises(ValueError, match="LOGIN_WINDOW_SECONDS"):
        create_app({"TESTING": True, "SECRET_KEY": "test-only", "LOGIN_WINDOW_SECONDS": 0})
    secret = "test-only-independent-placeholder-for-validation"
    with pytest.raises(RuntimeError, match="AUDIT_INTEGRITY_KEY"):
        create_app({"TESTING": False, "SECRET_KEY": secret, "AUDIT_INTEGRITY_KEY": secret})


def session_row(app, client):
    with client.session_transaction() as cookie:
        raw = cookie["session_token"]
    hashed = sha256(raw.encode()).hexdigest()
    with app.app_context():
        row = db.session.scalar(db.select(AuthSession).where(AuthSession.token_digest == hashed))
        assert row.token_digest != raw
        assert row.expires_at - row.created_at == 8 * 3600
        return row.id, raw


def protected(client):
    return client.get("/dashboard/student").status_code


def test_individual_sessions_and_current_logout(demo):
    app, _ = demo
    first, second = sign_in(app, "dahlia"), sign_in(app, "dahlia")
    unrelated = sign_in(app, "elm")
    first_id, first_token = session_row(app, first)
    second_id, second_token = session_row(app, second)
    unrelated_id, _ = session_row(app, unrelated)
    assert first_id != second_id and first_token != second_token

    page = first.get("/sessions")
    assert b"Current session" in page.data and b"Other session" in page.data
    assert first_token.encode() not in page.data and second_token.encode() not in page.data
    path = f"/sessions/{second_id}/revoke"
    assert first.post(path).status_code == 400
    assert first.post(f"/sessions/{unrelated_id}/revoke", data={"csrf_token": token(page)}).status_code == 404
    assert first.post(path, data={"csrf_token": token(page)}).status_code == 303
    assert protected(second) == 302 and protected(first) == protected(unrelated) == 200
    assert first.post("/logout", data={"csrf_token": token(first.get("/sessions"))}).status_code == 303
    with app.app_context():
        assert db.session.get(AuthSession, first_id).revoked_at is not None
        assert db.session.get(AuthSession, second_id).revoked_at is not None
        assert db.session.get(AuthSession, unrelated_id).revoked_at is None


def test_logout_everywhere(demo):
    app, _ = demo
    first, second = sign_in(app, "dahlia"), sign_in(app, "dahlia")
    assert first.post("/sessions/revoke-all", data={"csrf_token": token(first.get("/sessions"))}).status_code == 303
    assert protected(first) == protected(second) == 302


def test_server_deadline_and_password_reset_persist_revocations(demo, monkeypatch):
    app, ids = demo
    now = 1_000_000
    monkeypatch.setattr("app.session_security.time", lambda: now)
    expired = sign_in(app, "dahlia")
    expired_id, _ = session_row(app, expired)
    now += 8 * 3600
    assert protected(expired) == 302
    fresh = sign_in(app, "dahlia")
    fresh_id, _ = session_row(app, fresh)
    admin = sign_in(app, "atlas")
    assert submit(admin, f"/users/{ids['dahlia']}/password", password="fictional-after-password-reset").status_code == 303
    assert protected(fresh) == 302
    with app.app_context():
        assert db.session.get(AuthSession, expired_id).expires_at == now
        assert db.session.get(AuthSession, fresh_id).revoked_at is not None


def test_decision_role_is_historical(demo):
    app, ids = demo
    student = sign_in(app, "elm")
    assert protected(student) == 200
    admin = sign_in(app, "atlas")
    data = account_fields(ids, username="elm", role_id=ids["Teacher"], assigned_teacher_id=0)
    assert submit(admin, f"/users/{ids['elm']}/edit", **data).status_code == 303
    assert student.get("/dashboard/teacher").status_code == 200
    with app.app_context():
        roles = db.session.scalars(db.select(AccessLog.actor_role)
                                   .where(AccessLog.actor_user_id == ids["elm"])
                                   .order_by(AccessLog.id)).all()
        assert roles == ["Student", "Teacher"]
    page = admin.get("/access-logs?q=elm")
    assert page.status_code == 200
    assert b"Role at decision" in page.data and b"Audit chain verified locally" in page.data


@pytest.mark.parametrize("statement,values", [
    ("UPDATE student_records SET student_user_id=:birch WHERE id=:first", ("birch", "first")),
    ("UPDATE users SET assigned_teacher_id=:elm WHERE id=:dahlia", ("elm", "dahlia")),
    ("UPDATE users SET assigned_teacher_id=:birch WHERE id=:atlas", ("birch", "atlas")),
    ("UPDATE users SET role_id=:Teacher WHERE id=:dahlia", ("Teacher", "dahlia")),
    ("UPDATE users SET role_id=:Admin WHERE id=:birch", ("Admin", "birch")),
    ("UPDATE users SET role_id=:Teacher WHERE id=:atlas", ("Teacher", "atlas")),
    ("DELETE FROM users WHERE id=:atlas", ("atlas",)),
    ("UPDATE student_records SET marks=101 WHERE id=:first", ("first",)),
    ("INSERT INTO student_records(student_user_id, course, marks) VALUES (:dahlia, 'Test', 80)", ("dahlia",)),
])
def test_database_rejects_invalid_relations_and_last_admin(demo, statement, values):
    app, ids = demo
    with app.app_context(), db.engine.connect() as connection:
        with pytest.raises(IntegrityError):
            connection.execute(text(statement), {name: ids[name] for name in values})
        connection.rollback()


def test_audit_hmac_known_payload_and_append_only(demo):
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    entry = dict(id=1, actor_user_id=None, actor_role=None, action="test", resource="record",
                 decision="Allowed", timestamp=stamp, previous_mac=GENESIS)
    expected_bytes = b'["securerole:audit:v1",1,null,null,"test","record","Allowed","2026-01-01T00:00:00.000000+00:00","' + GENESIS.encode() + b'"]'
    assert entry_mac(b"fictional-key", entry) == hmac_new(b"fictional-key", expected_bytes, "sha256").hexdigest()
    app, ids = demo
    with app.app_context():
        db.session.add_all([AccessLog(actor_user_id=ids["atlas"], action="test", resource="record", decision="Allowed"),
                            AccessLog(action="test", resource="dashboard", decision="Denied")])
        db.session.commit()
        result = inspect_audit(db.engine, audit_key())
        assert result.valid and result.count == 2 and result.head_id == 2
        assert inspect_audit(db.engine, audit_key(), (result.head_id, result.head_mac)).valid
        assert not inspect_audit(db.engine, audit_key(), (3, result.head_mac)).valid
        assert not inspect_audit(db.engine, b"unrelated-key").valid
        for statement in ("UPDATE access_logs SET resource='modified' WHERE id=1",
                          "DELETE FROM access_logs WHERE id=1"):
            with pytest.raises(IntegrityError, match="append-only"):
                db.session.execute(text(statement))
            db.session.rollback()
    command = app.test_cli_runner().invoke(args=["verify-audit", "--checkpoint", f"{result.head_id}:{result.head_mac}"])
    assert command.exit_code == 0 and "Entries checked: 2" in command.output


def test_verifier_rejects_inconsistent_fixture():
    # Populate a synthetic verifier fixture with a stale MAC and changed data.
    key = b"fictional-audit-key"
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        db.metadata.create_all(connection)
        entry = dict(id=1, actor_user_id=None, actor_role=None, action="test", resource="original",
                     decision="Allowed", timestamp="2026-01-01 00:00:00", previous_mac=GENESIS)
        mac = entry_mac(key, entry)
        connection.execute(text("INSERT INTO audit_chain_state VALUES (1, 1, :mac, :tag)"),
                           {"mac": mac, "tag": key_tag(key)})
        connection.execute(text("""
            INSERT INTO access_logs(id,action,resource,decision,timestamp,previous_mac,entry_mac)
            VALUES (1,'test','different','Allowed','2026-01-01 00:00:00',:previous,:mac)
        """), {"mac": mac, "previous": GENESIS})
        assert not verify_chain(connection, key).valid
    engine.dispose()


def test_concurrent_appends_advance_one_chain(demo):
    app, _ = demo

    def append(identity):
        with app.app_context():
            commit_access_log(actor_id=None, action="test.parallel", resource=f"fixture:{identity}", allowed=True)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(append, range(8)))
    with app.app_context():
        result = inspect_audit(db.engine, audit_key())
        assert result.valid and result.count == result.head_id == 8


def test_legacy_migration_preserves_rows_and_unknown_role(tmp_path):
    path = tmp_path / "legacy.db"
    backup = tmp_path / "backup.db"
    app = create_app({"TESTING": True, "SECRET_KEY": "test-source",
                      "SQLALCHEMY_DATABASE_URI": f"sqlite:///{path}"})
    with app.app_context(), db.engine.begin() as connection:
        db.metadata.create_all(connection, tables=[Role.__table__, User.__table__, StudentRecord.__table__])
        connection.exec_driver_sql("""
            CREATE TABLE access_logs (
                id INTEGER PRIMARY KEY, actor_user_id INTEGER REFERENCES users(id),
                action TEXT NOT NULL, resource TEXT NOT NULL, decision TEXT NOT NULL,
                timestamp DATETIME NOT NULL
            )
        """)
        connection.exec_driver_sql("INSERT INTO roles (id,name) VALUES (1,'Admin'),(2,'Student')")
        admin = User()
        admin.set_password(PASSWORD)
        connection.exec_driver_sql(
            "INSERT INTO users (id,username,password_hash,display_name,role_id) VALUES "
            "(1,'admin',?,'Admin',1),(2,'student',?,'Student',2)",
            (admin.password_hash, admin.password_hash),
        )
        connection.exec_driver_sql("INSERT INTO student_records VALUES (7,2,'Legacy course',88)")
        connection.exec_driver_sql("INSERT INTO access_logs VALUES (4,1,'legacy','record','Allowed','2026-01-01 00:00:00')")
    runner = app.test_cli_runner()
    assert runner.invoke(args=["backup-db", str(backup)]).exit_code == 0
    assert runner.invoke(args=["backup-db", str(backup)]).exit_code != 0
    assert runner.invoke(args=["migrate-db"]).exit_code == 0
    assert "already current" in runner.invoke(args=["migrate-db"]).output
    with app.app_context():
        assert not migrate_database()
        assert db.session.get(StudentRecord, 7).course == "Legacy course"
        assert db.session.get(User, 1).check_password(PASSWORD)
        legacy = db.session.get(AccessLog, 4)
        assert (legacy.actor_user_id, legacy.actor_role, legacy.resource) == (1, None, "record")
        assert inspect_audit(db.engine, audit_key()).valid
        db.session.remove()
    client = sign_in(app, "admin")
    page = client.get("/access-logs?q=legacy")
    assert b"Unknown" in page.data
    with sqlite3.connect(backup) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (0,)
        assert connection.execute("SELECT id FROM access_logs").fetchone() == (4,)
        assert "actor_role" not in {row[1] for row in connection.execute("PRAGMA table_info(access_logs)")}
