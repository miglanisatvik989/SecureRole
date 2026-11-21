"""Unified demo initialization and preservation checks."""

import csv
from pathlib import Path
from stat import S_IMODE

from sqlalchemy import text

from app.audit_integrity import audit_key, inspect_audit
from app.demo_data import SUBJECTS, TEAM_ACCOUNTS
from app.models import AccessLog, StudentRecord, User, db


def users():
    return {user.username: user for user in db.session.scalars(db.select(User))}


def private_file():
    return Path(db.engine.url.database).with_suffix(".demo-credentials.csv")


def test_setup_unifies_roster_preserves_extras_and_repeats(app, monkeypatch):
    runner = app.test_cli_runner()
    starter = runner.invoke(args=["seed-db"])
    assert starter.exit_code == 0
    original = users()
    old_hashes = {username: account.password_hash for username, account in original.items()}
    extra = User(username="existing-account", display_name="Existing", role=original["student1"].role,
                 assigned_teacher=original["teacher1"])
    extra.set_password("fictional-existing-password")
    db.session.add(StudentRecord(student=extra, course="Existing academic course", marks=91))
    db.session.add(AccessLog(actor=original["admin"], action="test.fixture", resource="fixture", decision="Allowed"))
    db.session.commit()
    audit_before = inspect_audit(db.engine, audit_key())

    local_password = "fictional-team-password"
    monkeypatch.setenv("DEMO_SHUBHAM_PASSWORD", local_password)
    result = runner.invoke(args=["setup-demo"])
    assert result.exit_code == 0, result.output
    assert "Accounts: 140 (3 Admins, 14 Teachers, 123 Students)" in result.output
    assert "Academic records: 112. Awaiting records: 11." in result.output
    assert local_password not in result.output
    db.session.expire_all()
    current = users()
    for account in TEAM_ACCOUNTS:
        assert current[account.username].role.name == account.role
        teacher = current[account.username].assigned_teacher
        assert (teacher.username if teacher else None) == account.teacher
        if account.marks is not None:
            assert current[account.username].student_record.course == SUBJECTS[0]
            assert current[account.username].student_record.marks == 88
    assert current["kunal"].student_record is None
    assert current["existing-account"].student_record.course == "Existing academic course"
    assert {name: current[name].password_hash for name in original} == old_hashes
    assert inspect_audit(db.engine, audit_key()) == audit_before
    assert db.session.execute(text("PRAGMA integrity_check")).scalar_one() == "ok"
    assert db.session.execute(text("PRAGMA foreign_key_check")).all() == []
    path = private_file()
    before = path.read_bytes()
    assert S_IMODE(path.stat().st_mode) == 0o600
    with path.open(encoding="utf-8", newline="") as stream:
        credentials = {row["username"]: row["password"] for row in csv.DictReader(stream)}
    for account in TEAM_ACCOUNTS:
        assert current[account.username].check_password(credentials[account.username])
    assert credentials["shubham"] == local_password

    monkeypatch.setenv("DEMO_SHUBHAM_PASSWORD", "different-fictional-value")
    repeated = runner.invoke(args=["setup-demo"])
    assert repeated.exit_code == 0
    assert "Added 0 accounts and 0 records" in repeated.output
    assert path.read_bytes() == before
    db.session.expire_all()
    assert current["shubham"].check_password(local_password)


def test_short_private_password_rejects_whole_transaction(app, monkeypatch):
    monkeypatch.setenv("DEMO_SATVIK_PASSWORD", "short")
    fixture = User()
    fixture.set_password("fictional-test-password")
    monkeypatch.setattr(User, "set_password", lambda user, password: setattr(user, "password_hash", fixture.password_hash))
    result = app.test_cli_runner().invoke(args=["setup-demo"])
    assert result.exit_code != 0
    assert "must have 12–128 characters" in result.output
    assert not users()
    assert not private_file().exists()


def test_setup_extends_file_without_replacing_previous_credentials(app, monkeypatch):
    # Use one synthetic hash during the large fictional fixture population.
    fixture = User()
    fixture.set_password("fictional-fixture-password")
    monkeypatch.setattr(User, "set_password", lambda user, password: setattr(user, "password_hash", fixture.password_hash))
    runner = app.test_cli_runner()
    assert runner.invoke(args=["seed-demo"]).exit_code == 0
    path = private_file()
    original = path.read_bytes()
    result = runner.invoke(args=["setup-demo"])
    assert result.exit_code == 0, result.output
    assert "Accounts: 139 (3 Admins, 14 Teachers, 122 Students)" in result.output
    assert "Academic records: 111. Awaiting records: 11." in result.output
    assert "Added 5 accounts and 1 records" in result.output
    assert path.read_bytes().startswith(original)
    with path.open(encoding="utf-8", newline="") as stream:
        assert len(list(csv.DictReader(stream))) == 139
    assert runner.invoke(args=["seed-demo"]).exit_code == 0
