from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError, StatementError

from app import create_app, login_manager
from app.models import AccessLog, Role, StudentRecord, User, db


def user(username):
    return db.session.scalar(db.select(User).filter_by(username=username))


def counts():
    return tuple(db.session.scalar(db.select(db.func.count()).select_from(model))
                 for model in (Role, User, StudentRecord, AccessLog))


def test_factory_and_database_location():
    app = create_app({"TESTING": True, "SECRET_KEY": "test-only"})
    with app.app_context():
        assert db.engine.url.database == f"{app.instance_path}/securerole.db"
        assert app.login_manager is login_manager
        assert login_manager._user_callback("invalid-id") is None


def test_missing_secret_has_clear_error():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app({"SECRET_KEY": None})


def test_init_db_is_repeatable(app):
    runner = app.test_cli_runner()
    assert runner.invoke(args=["init-db"]).exit_code == 0
    assert runner.invoke(args=["init-db"]).exit_code == 0
    assert set(inspect(db.engine).get_table_names()) == {
        "roles", "users", "student_records", "access_logs", "auth_sessions", "login_windows", "audit_chain_state"
    }
    assert counts() == (0, 0, 0, 0)


def test_fresh_seed_and_passwords(app):
    result = app.test_cli_runner().invoke(args=["seed-db"])
    assert result.exit_code == 0, result.output
    assert counts() == (3, 6, 2, 0)
    credentials = dict(line.split(": ", 1) for line in result.output.splitlines()
                       if line.startswith(tuple(f"{name}: " for name in (
                           "admin", "teacher1", "teacher2", "student1", "student2", "student3"
                       ))))
    assert len(credentials) == 6
    assert len(set(credentials.values())) == 6
    for username, password in credentials.items():
        account = user(username)
        assert account.password_hash != password
        assert account.check_password(password)
        assert not account.check_password("wrong-password")
        assert account.display_name
        assert account.email is None
        assert account.is_authenticated
    assert user("admin").role.name == "Admin"
    for name in ("teacher1", "teacher2"):
        assert user(name).role.name == "Teacher"
        assert user(name).assigned_teacher is None
        assert user(name).student_record is None
    assert user("admin").student_record is None
    assert user("admin").assigned_teacher is None
    assert {s.username for s in user("teacher1").assigned_students} == {"student1", "student2"}
    assert {s.username for s in user("teacher2").assigned_students} == {"student3"}
    assert user("student2").student_record is None
    for name, teacher, marks in (("student1", "teacher1", 85), ("student3", "teacher2", 78)):
        account = user(name)
        assert account.role.name == "Student"
        assert account.assigned_teacher == user(teacher)
        assert account.student_record.marks == marks
        assert account.student_record.course == "Cryptography and Network Security"
    assert login_manager._user_callback(str(user("admin").id)) == user("admin")


def test_reseed_preserves_existing_data(seeded):
    hashes = {u.username: u.password_hash for u in db.session.scalars(db.select(User))}
    user("student1").student_record.marks = 91
    user("student1").assigned_teacher = user("teacher2")
    user("admin").display_name = "Edited name"
    db.session.add(AccessLog(action="test", resource="test", decision="Allowed"))
    db.session.commit()
    result = seeded.test_cli_runner().invoke(args=["seed-db"])
    assert result.exit_code == 0, result.output
    assert "New demo credentials" not in result.output
    assert counts() == (3, 6, 2, 1)
    assert hashes == {u.username: u.password_hash for u in db.session.scalars(db.select(User))}
    assert user("student1").student_record.marks == 91
    assert user("student1").assigned_teacher == user("teacher2")
    assert user("admin").display_name == "Edited name"


def test_seed_completes_partial_database(app):
    db.session.add(Role(name="Student"))
    db.session.commit()
    assert app.test_cli_runner().invoke(args=["seed-db"]).exit_code == 0
    assert counts() == (3, 6, 2, 0)


def test_conflicting_seed_rolls_back(app):
    student_role = Role(name="Student")
    account = User(username="teacher2", display_name="Existing", role=student_role)
    account.set_password("existing-password")
    db.session.add(account)
    db.session.commit()
    result = app.test_cli_runner().invoke(args=["seed-db"])
    assert result.exit_code != 0
    assert "does not have the demo role" in result.output
    assert "New demo credentials" not in result.output
    assert counts() == (1, 1, 0, 0)
    assert user("teacher2").check_password("existing-password")


@pytest.mark.parametrize("recipient,teacher", [
    ("admin", "teacher1"), ("teacher1", "teacher2"),
    ("student1", "admin"), ("student1", "student2"), ("student1", "student1"),
])
@pytest.mark.parametrize("via_fk", [False, True])
def test_invalid_teacher_assignments(seeded, recipient, teacher, via_fk):
    account = user(recipient)
    target = user(teacher)
    # Load old relationships to verify direct FK edits cannot use stale cached values.
    _ = account.assigned_teacher
    if via_fk:
        account.assigned_teacher_id = target.id
    else:
        account.assigned_teacher = target
    with pytest.raises(ValueError, match="Student|Teacher"):
        db.session.commit()
    db.session.rollback()


@pytest.mark.parametrize("via_fk", [False, True])
def test_valid_reassignment_and_unassignment(seeded, via_fk):
    account = user("student1")
    _ = account.assigned_teacher
    if via_fk:
        account.assigned_teacher_id = user("teacher2").id
    else:
        account.assigned_teacher = user("teacher2")
    db.session.commit()
    assert account.assigned_teacher == user("teacher2")
    if via_fk:
        account.assigned_teacher_id = None
    else:
        account.assigned_teacher = None
    db.session.commit()
    assert account.assigned_teacher is None


@pytest.mark.parametrize("username", ["admin", "teacher1"])
@pytest.mark.parametrize("via_fk", [False, True])
def test_only_students_own_records(seeded, username, via_fk):
    owner = user(username)
    record = StudentRecord(course="Test course", marks=50)
    if via_fk:
        record.student_user_id = owner.id
    else:
        record.student = owner
    db.session.add(record)
    with pytest.raises(ValueError, match="Only Student"):
        db.session.commit()
    db.session.rollback()


@pytest.mark.parametrize("via_fk", [False, True])
def test_existing_record_cannot_transfer_to_teacher(seeded, via_fk):
    record = user("student1").student_record
    _ = record.student
    if via_fk:
        record.student_user_id = user("teacher1").id
    else:
        record.student = user("teacher1")
    with pytest.raises(ValueError, match="Only Student"):
        db.session.commit()
    db.session.rollback()


@pytest.mark.parametrize("username,role_name", [
    ("teacher1", "Admin"), ("student1", "Admin"), ("student3", "Teacher")
])
@pytest.mark.parametrize("via_fk", [False, True])
def test_role_changes_revalidate_dependents(seeded, username, role_name, via_fk):
    account = user(username)
    _ = account.role
    role = db.session.scalar(db.select(Role).filter_by(name=role_name))
    if via_fk:
        account.role_id = role.id
    else:
        account.role = role
    with pytest.raises(ValueError):
        db.session.commit()
    db.session.rollback()


def test_record_owner_role_change_without_assignment(seeded):
    account = user("student1")
    account.assigned_teacher = None
    db.session.commit()
    account.role = user("admin").role
    with pytest.raises(ValueError, match="Only Student"):
        db.session.commit()
    db.session.rollback()


@pytest.mark.parametrize("marks", [-1, 101, "not-a-number", float("nan"), float("inf"), None])
def test_invalid_marks_in_orm(seeded, marks):
    user("student1").student_record.marks = marks
    with pytest.raises(ValueError, match="Marks"):
        db.session.commit()
    db.session.rollback()


@pytest.mark.parametrize("marks", [0, 100, Decimal("85.25")])
def test_valid_marks(seeded, marks):
    record = user("student1").student_record
    record.marks = marks
    db.session.commit()
    assert record.marks == marks


# Raw SQL tests deliberately bypass Python validation to test SQLite itself.
@pytest.mark.parametrize("statement", [
    "INSERT INTO roles (name) VALUES ('Admin')",
    "INSERT INTO roles (name) VALUES ('Unsupported')",
    "INSERT INTO roles (name) VALUES (NULL)",
    "UPDATE users SET username = 'admin' WHERE username = 'teacher1'",
    "UPDATE users SET role_id = 999999 WHERE username = 'student2'",
    "UPDATE users SET assigned_teacher_id = 999999 WHERE username = 'student2'",
    "UPDATE users SET role_id = NULL WHERE username = 'student2'",
    "UPDATE users SET username = NULL WHERE username = 'student2'",
    "UPDATE users SET display_name = NULL WHERE username = 'student2'",
    "UPDATE users SET password_hash = NULL WHERE username = 'student2'",
    "UPDATE student_records SET marks = -1",
    "UPDATE student_records SET marks = 101",
    "UPDATE student_records SET marks = NULL",
    "UPDATE student_records SET course = NULL",
    "UPDATE student_records SET student_user_id = NULL",
    "UPDATE student_records SET student_user_id = 999999",
    "INSERT INTO student_records (student_user_id, course, marks) "
    "SELECT student_user_id, 'Duplicate', 50 FROM student_records LIMIT 1",
    "INSERT INTO access_logs (action, resource, decision, timestamp) "
    "VALUES ('test', 'test', 'Maybe', '2026-01-01 00:00:00')",
    "INSERT INTO access_logs (actor_user_id, action, resource, decision, timestamp) "
    "VALUES (999999, 'test', 'test', 'Allowed', '2026-01-01 00:00:00')",
    "INSERT INTO access_logs (resource, decision, timestamp) "
    "VALUES ('test', 'Allowed', '2026-01-01 00:00:00')",
    "INSERT INTO access_logs (action, decision, timestamp) "
    "VALUES ('test', 'Allowed', '2026-01-01 00:00:00')",
    "INSERT INTO access_logs (action, resource, timestamp) "
    "VALUES ('test', 'test', '2026-01-01 00:00:00')",
    "INSERT INTO access_logs (action, resource, decision) VALUES ('test', 'test', 'Allowed')",
    "DELETE FROM users WHERE username = 'teacher1'",
    "DELETE FROM users WHERE username = 'student1'",
    "DELETE FROM roles WHERE name = 'Student'",
])
def test_sqlite_constraints(seeded, statement):
    assert db.session.scalar(text("PRAGMA foreign_keys")) == 1
    with pytest.raises(IntegrityError):
        db.session.execute(text(statement))
        db.session.commit()
    db.session.rollback()
    assert counts() == (3, 6, 2, 0)


def test_foreign_keys_on_new_connection(seeded):
    with db.engine.connect() as first, db.engine.connect() as second:
        assert first.scalar(text("PRAGMA foreign_keys")) == 1
        assert second.scalar(text("PRAGMA foreign_keys")) == 1
    assert db.session.execute(text("PRAGMA foreign_key_check")).all() == []


def test_unique_email_allows_multiple_nulls(seeded):
    user("student1").email = "student@example.test"
    db.session.commit()
    user("student2").email = "student@example.test"
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
    assert user("student2").email is None


@pytest.mark.parametrize("decision", ["Allowed", "Denied"])
def test_access_logs_and_utc_round_trip(seeded, decision):
    before = datetime.now(timezone.utc)
    log = AccessLog(actor=user("admin"), action="test", resource="record", decision=decision)
    anonymous = AccessLog(action="test", resource="record", decision=decision)
    db.session.add_all([log, anonymous])
    db.session.commit()
    assert before <= log.timestamp <= datetime.now(timezone.utc)
    assert log.timestamp.utcoffset() == timedelta(0)
    assert log.actor == user("admin")
    assert anonymous.actor is None
    local_time = datetime(2026, 1, 1, 12, tzinfo=timezone(timedelta(hours=5)))
    converted = AccessLog(action="test", resource="record", decision=decision, timestamp=local_time)
    db.session.add(converted)
    db.session.commit()
    assert converted.timestamp == datetime(2026, 1, 1, 7, tzinfo=timezone.utc)


def test_naive_timestamp_is_rejected(app):
    db.session.add(AccessLog(action="test", resource="test", decision="Allowed",
                             timestamp=datetime(2026, 1, 1)))
    with pytest.raises(StatementError, match="timezone"):
        db.session.commit()
    db.session.rollback()
