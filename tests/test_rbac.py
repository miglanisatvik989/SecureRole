import re
from datetime import timezone

import pytest
from flask import request
from sqlalchemy import update

from app import create_app
from app.models import AccessLog, Role, StudentRecord, User, db
from app.rbac import Action, is_allowed, require_permission, scoped_records


@pytest.fixture(scope="module")
def password_hash():
    user = User()
    user.set_password("fictional-test-password")
    return user.password_hash


@pytest.fixture
def policy(tmp_path, password_hash):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-only-key",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'rbac.db'}",
    })

    @app.post("/test/records/<int:student_id>")
    def create_record(student_id):
        require_permission(Action.CREATE_RECORD, student_id=student_id, atomic=True)
        db.session.add(StudentRecord(student_user_id=student_id, course="Test course", marks=80))
        if request.args.get("rollback"):
            db.session.rollback()
            return "", 409
        db.session.commit()
        return "", 201

    with app.app_context():
        db.create_all()
        roles = {name: Role(name=name) for name in ("Admin", "Teacher", "Student")}

        def account(name, role, teacher=None):
            return User(username=name, display_name=name.title(), role=roles[role],
                        password_hash=password_hash, assigned_teacher=teacher)

        admin = account("admin", "Admin")
        teacher = account("teacher", "Teacher")
        other_teacher = account("other_teacher", "Teacher")
        student = account("student", "Student", teacher)
        other = account("other", "Student", other_teacher)
        unassigned = account("unassigned", "Student")
        new_student = account("new_student", "Student", teacher)
        db.session.add_all([admin, teacher, other_teacher, student, other, unassigned, new_student])
        students = (student, other, unassigned)
        records = [StudentRecord(student=user, course="Test course", marks=75) for user in students]
        db.session.add_all(records)
        db.session.commit()

        users = {u.username: u.id for u in (admin, teacher, other_teacher, *students, new_student)}
        record_ids = {u.username: r.id for u, r in zip(students, records)}
    yield app, users, record_ids
    with app.app_context():
        db.engine.dispose()


@pytest.mark.parametrize("name,expected", [
    ("admin", (True, True, True, True, True, True, True, True)),
    ("teacher", (True, True, True, False, False, False, False, False)),
    ("student", (True, False, False, False, False, False, False, False)),
])
def test_permission_matrix(policy, name, expected):
    app, users, records = policy
    with app.app_context():
        actor = users[name]
        actual = (
            is_allowed(actor, Action.VIEW_RECORD, record_id=records["student"]),
            is_allowed(actor, Action.CREATE_RECORD, student_id=users["new_student"]),
            is_allowed(actor, Action.EDIT_RECORD, record_id=records["student"]),
            is_allowed(actor, Action.DELETE_RECORD, record_id=records["student"]),
            is_allowed(actor, Action.MANAGE_USERS),
            is_allowed(actor, Action.ASSIGN_ROLES),
            is_allowed(actor, Action.ASSIGN_TEACHERS),
            is_allowed(actor, Action.VIEW_ACCESS_LOGS),
        )
        assert actual == expected


def test_record_scope_and_creation_target(policy):
    app, users, records = policy
    with app.app_context():
        for target in ("other", "unassigned"):
            for action in (Action.VIEW_RECORD, Action.EDIT_RECORD, Action.DELETE_RECORD):
                assert is_allowed(users["admin"], action, record_id=records[target])
                assert not is_allowed(users["teacher"], action, record_id=records[target])
                assert not is_allowed(users["student"], action, record_id=records[target])
            assert is_allowed(users["admin"], Action.CREATE_RECORD, student_id=users[target])
            assert not is_allowed(users["teacher"], Action.CREATE_RECORD, student_id=users[target])
        assert is_allowed(users["teacher"], Action.CREATE_RECORD, student_id=users["new_student"])
        assert not is_allowed(users["admin"], Action.CREATE_RECORD, student_id=users["teacher"])


def test_default_denials(policy):
    app, users, records = policy
    with app.app_context():
        admin = users["admin"]
        assert not is_allowed(admin, "unrecognized")
        assert not is_allowed(admin, Action.VIEW_RECORD)
        assert not is_allowed(admin, Action.VIEW_RECORD, student_id=users["student"])
        assert not is_allowed(admin, Action.VIEW_RECORD, record_id=records["student"], student_id=users["student"])
        assert not is_allowed(admin, Action.VIEW_RECORD, record_id=999999)
        assert not is_allowed(admin, Action.CREATE_RECORD, student_id=999999)
        assert not is_allowed(admin, Action.CREATE_RECORD, record_id=records["student"])
        assert not is_allowed(admin, Action.VIEW_ACCESS_LOGS, student_id=users["student"])
        assert not is_allowed(admin, Action.VIEW_DASHBOARD, dashboard_role="Unknown")
        for actor in (None, True, -1, "1", 999999, 2**63):
            assert not is_allowed(actor, Action.VIEW_ACCESS_LOGS)
            assert not is_allowed(actor, Action.VIEW_RECORD, record_id=records["student"])


def test_query_scopes(policy):
    app, users, records = policy
    with app.app_context():
        def visible(actor, action=Action.VIEW_RECORD):
            return {record.id for record in db.session.scalars(scoped_records(actor, action))}

        assert visible(users["admin"]) == set(records.values())
        assert visible(users["teacher"]) == {records["student"]}
        assert visible(users["other_teacher"]) == {records["other"]}
        assert visible(users["student"]) == {records["student"]}
        assert visible(users["teacher"], Action.EDIT_RECORD) == {records["student"]}
        assert visible(users["teacher"], Action.DELETE_RECORD) == set()
        assert visible(users["student"], Action.EDIT_RECORD) == set()
        assert visible(users["admin"], Action.DELETE_RECORD) == set(records.values())
        assert visible(users["admin"], Action.CREATE_RECORD) == set()
        assert visible(users["admin"], "unknown") == set()
        assert visible(None) == set()


def test_scopes_read_latest_assignment_even_with_cached_owner(policy):
    app, users, records = policy
    with app.app_context():
        owner = db.session.get(User, users["student"])
        assert owner.assigned_teacher_id == users["teacher"]
        query = scoped_records(users["teacher"])
        with db.engine.begin() as connection:
            connection.execute(update(User).where(User.id == owner.id)
                               .values(assigned_teacher_id=users["other_teacher"]))
        assert owner.assigned_teacher_id == users["teacher"]
        assert not is_allowed(users["teacher"], Action.EDIT_RECORD, record_id=records["student"])
        assert is_allowed(users["other_teacher"], Action.EDIT_RECORD, record_id=records["student"])
        assert db.session.scalars(query).all() == []


def csrf_token(page):
    return re.search(rb'name="csrf_token"[^>]+value="([^"]+)"', page.data).group(1).decode()


def login(client, username):
    token = csrf_token(client.get("/login"))
    assert client.post("/login", data={
        "username": username, "password": "fictional-test-password", "csrf_token": token
    }).status_code == 303


def test_dashboard_guard_403_and_audit(policy):
    app, users, _ = policy
    with app.test_client() as client:
        assert client.get("/dashboard/teacher").status_code == 302
        login(client, "student")
        response = client.get("/dashboard/admin", query_string={"private": "omit-this"})
        assert response.status_code == 403
        assert b"Access restricted" in response.data
        assert b"You don't have permission to perform this action." in response.data
        assert b"Back to dashboard" in response.data
        assert b'href="/dashboard"' in response.data
        assert b"omit-this" not in response.data
        assert "no-store" in response.headers["Cache-Control"]
        assert client.get("/dashboard").status_code == 302
        assert client.get("/dashboard/student").status_code == 200
    with app.app_context():
        logs = db.session.scalars(db.select(AccessLog).order_by(AccessLog.id)).all()
        assert [(log.actor_user_id, log.action, log.resource, log.decision) for log in logs] == [
            (None, Action.VIEW_DASHBOARD, "dashboard:teacher", "Denied"),
            (users["student"], Action.VIEW_DASHBOARD, "dashboard:admin", "Denied"),
            (users["student"], Action.VIEW_DASHBOARD, "dashboard", "Allowed"),
            (users["student"], Action.VIEW_DASHBOARD, "dashboard:student", "Allowed"),
        ]
        assert all(log.timestamp.tzinfo == timezone.utc for log in logs)


def test_dashboard_refreshes_role_after_login(policy):
    app, users, _ = policy
    with app.test_client() as client:
        login(client, "other")
        with app.app_context():
            account = db.session.get(User, users["other"])
            db.session.delete(account.student_record)
            account.assigned_teacher = None
            account.role = db.session.scalar(db.select(Role).filter_by(name="Teacher"))
            db.session.commit()
        assert client.get("/dashboard/student").status_code == 403
        assert client.get("/dashboard").location == "/dashboard/teacher"
        assert client.get("/dashboard/teacher").status_code == 200


def test_guard_commits_allowed_write_and_log_together(policy):
    app, users, _ = policy
    with app.test_client() as client:
        login(client, "teacher")
        token = csrf_token(client.get("/dashboard/teacher"))
        data = {"csrf_token": token}
        target = users["new_student"]
        denied = users["unassigned"]
        response = client.post(f"/test/records/{denied}", data=data)
        assert response.status_code == 403
        assert "no-store" in response.headers["Cache-Control"]
        assert client.post(f"/test/records/{target}?rollback=1", data=data).status_code == 409
        with app.app_context():
            assert db.session.scalar(db.select(StudentRecord).filter_by(student_user_id=target)) is None
            decisions = db.session.scalars(db.select(AccessLog.decision).filter_by(action=Action.CREATE_RECORD)).all()
            assert decisions == ["Denied"]
        assert client.post(f"/test/records/{target}", data=data).status_code == 201
    with app.app_context():
        assert db.session.scalar(db.select(StudentRecord).filter_by(student_user_id=target)) is not None
        logs = db.session.scalars(
            db.select(AccessLog).filter_by(action=Action.CREATE_RECORD).order_by(AccessLog.id)
        ).all()
        assert [(log.actor_user_id, log.resource, log.decision) for log in logs] == [
            (users["teacher"], f"student:{denied}", "Denied"),
            (users["teacher"], f"student:{target}", "Allowed"),
        ]
