import csv
from collections import Counter
from pathlib import Path
from stat import S_IMODE

import pytest
from sqlalchemy import text

from app.audit_integrity import audit_key, inspect_audit
from app.demo_data import EMAIL_DOMAIN, SUBJECTS, plan_demo
from app.models import AccessLog, Role, StudentRecord, User, db


def roster():
    return {user.username: user for user in db.session.scalars(db.select(User))}


def signature(user):
    record = user.student_record
    return (user.id, user.display_name, user.role.name, user.assigned_teacher_id, user.password_hash,
            (record.id, record.course, record.marks) if record is not None else None)


def credentials_path():
    return Path(db.engine.url.database).with_suffix(".demo-credentials.csv")


def check_distribution(users):
    assert Counter(user.role.name for user in users.values()) == {"Admin": 2, "Teacher": 12, "Student": 120}
    students = [user for user in users.values() if user.role.name == "Student"]
    teachers = Counter(user.assigned_teacher.username for user in students)
    assert len(teachers) == 12 and set(teachers.values()) == {10}
    planned = {item.username: item for item in plan_demo()}
    assert Counter(planned[name].subject for name in teachers) == dict.fromkeys(SUBJECTS, 2)
    assert Counter(planned[user.assigned_teacher.username].subject for user in students) == dict.fromkeys(SUBJECTS, 20)
    records = [user.student_record for user in students if user.student_record is not None]
    assert len(records) == 110
    assert all(0 <= record.marks <= 100 for record in records)
    assert len({record.marks for record in records}) > 35
    assert all(record.course == planned[record.student.username].subject for record in records)
    emails = [user.email.casefold() for user in users.values()]
    assert len(set(emails)) == 134 and all(email.endswith("@" + EMAIL_DOMAIN) for email in emails)
    assert not db.session.execute(text("PRAGMA foreign_key_check")).all()


def test_expansion_preserves_original_data_credentials_and_audit(seeded):
    original = roster()
    original["admin"].email = "original-admin@" + EMAIL_DOMAIN
    db.session.add(AccessLog(actor=original["admin"], action="test.fixture", resource="fixture", decision="Allowed"))
    db.session.commit()
    baseline = {username: signature(user) for username, user in original.items()}
    previous = inspect_audit(db.engine, audit_key())
    runner = seeded.test_cli_runner()
    result = runner.invoke(args=["seed-demo"])
    assert result.exit_code == 0, result.output
    assert "Added 128 accounts and 108 records" in result.output
    db.session.expire_all()
    users = roster()
    check_distribution(users)
    assert users["admin"].email == "original-admin@" + EMAIL_DOMAIN
    assert users["student2"].student_record is None
    assert {username: signature(users[username]) for username in baseline} == baseline
    assert inspect_audit(db.engine, audit_key()) == previous

    path = credentials_path()
    assert S_IMODE(path.stat().st_mode) == 0o600
    before = path.read_bytes()
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 128 and len({row["password"] for row in rows}) == 128
    assert not (set(baseline) & {row["username"] for row in rows})
    admin = next(row for row in rows if row["username"] == "ananya.rao")
    assert users["ananya.rao"].check_password(admin["password"])
    assert admin["password"] not in result.output

    repeat = runner.invoke(args=["seed-demo"])
    assert repeat.exit_code == 0, repeat.output
    assert "Added 0 accounts and 0 records" in repeat.output
    assert path.read_bytes() == before
    assert inspect_audit(db.engine, audit_key()) == previous


def test_fresh_expansion_and_repeat_preserve_an_added_record(app):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["seed-demo"])
    assert result.exit_code == 0, result.output
    assert "Added 134 accounts and 110 records" in result.output
    users = roster()
    check_distribution(users)
    assert users["student2"].student_record is None
    # Model a legitimate change that trades one recorded student for another.
    db.session.delete(users["varun.kulkarni"].student_record)
    db.session.add(StudentRecord(student=users["student2"], course=SUBJECTS[0], marks=74))
    db.session.commit()
    record_id = users["student2"].student_record.id
    assert runner.invoke(args=["seed-demo"]).exit_code == 0
    db.session.expire_all()
    assert users["student2"].student_record.id == record_id
    assert users["varun.kulkarni"].student_record is None


@pytest.mark.parametrize("condition,message", [
    ("unrelated", "outside the demonstration roster"),
    ("assignment", "teacher assignment conflicts"),
    ("course", "academic course conflicts"),
    ("credentials", "credentials file already exists"),
])
def test_existing_conflicts_abort_without_changes(seeded, condition, message):
    users = roster()
    if condition == "unrelated":
        extra = User(username="other-account", display_name="Other", role=users["admin"].role)
        extra.set_password("fictional-test-password")
        db.session.add(extra)
    elif condition == "assignment":
        users["student2"].assigned_teacher = users["teacher2"]
    elif condition == "course":
        users["student3"].student_record.course = "Different course"
    else:
        credentials_path().write_text("fixture should remain untouched", encoding="utf-8")
    db.session.commit()
    previous = {name: signature(user) for name, user in roster().items()}

    result = seeded.test_cli_runner().invoke(args=["seed-demo"])
    assert result.exit_code != 0 and message in result.output
    db.session.expire_all()
    assert {name: signature(user) for name, user in roster().items()} == previous
    if condition == "credentials":
        assert credentials_path().read_text(encoding="utf-8") == "fixture should remain untouched"
    else:
        assert not credentials_path().exists()


def test_credentials_write_failure_rolls_back_dataset(seeded, monkeypatch):
    baseline = roster()
    fictional_hash = baseline["admin"].password_hash
    monkeypatch.setattr(User, "set_password", lambda user, password: setattr(user, "password_hash", fictional_hash))

    def fail(*args):
        raise OSError("fixture I/O failure")

    monkeypatch.setattr("app.demo_seed.write_credentials", fail)
    result = seeded.test_cli_runner().invoke(args=["seed-demo"])
    assert result.exit_code != 0 and "could not be saved" in result.output
    db.session.expire_all()
    assert set(roster()) == set(baseline)
    assert all(user.email is None for user in roster().values())
    assert db.session.scalar(db.select(db.func.count(StudentRecord.id))) == 2
    assert not credentials_path().exists()
