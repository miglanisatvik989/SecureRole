"""Independent checks for the PBL acceptance criteria T1 through T11."""

from urllib.parse import urlsplit

import pytest

from app.models import AccessLog, StudentRecord, User, db
from app.rbac import Action, is_allowed
from tests.test_features import account_fields, demo, sign_in, token


CASES = [
    pytest.param("atlas", "GET", "/records", Action.LIST_RECORDS, "student_records", 200, id="T1"),
    pytest.param("atlas", "POST", "/records/{first}/delete", Action.DELETE_RECORD, "student_record:{first}", 303, id="T2"),
    pytest.param("birch", "POST", "/students/{elm}/record/new", Action.CREATE_RECORD, "student:{elm}", 303, id="T3"),
    pytest.param("birch", "POST", "/records/{first}/delete", Action.DELETE_RECORD, "student_record:{first}", 403, id="T4"),
    pytest.param("dahlia", "GET", "/records/{first}", Action.VIEW_RECORD, "student_record:{first}", 200, id="T5"),
    pytest.param("dahlia", "GET", "/records/{second}", Action.VIEW_RECORD, "student_record:{second}", 403, id="T6"),
    pytest.param("dahlia", "POST", "/records/{first}/edit", Action.EDIT_RECORD, "student_record:{first}", 403, id="T7"),
    pytest.param(None, "GET", "/dashboard/student", Action.VIEW_DASHBOARD, "dashboard:student", 302, id="T8"),
    pytest.param("dahlia", "GET", "/users", Action.MANAGE_USERS, "users", 403, id="T9"),
    pytest.param("birch", "POST", "/users/{elm}/edit", Action.MANAGE_USERS, "users", 403, id="T10"),
    pytest.param("birch", "GET", "/records/{second}", Action.VIEW_RECORD, "student_record:{second}", 403, id="T11"),
]


@pytest.mark.parametrize("actor,method,path,action,resource,expected", CASES)
def test_acceptance(demo, actor, method, path, action, resource, expected):
    app, ids = demo
    if actor == "birch" and action == Action.VIEW_RECORD:
        # T11 uses a student with no teacher assignment at all.
        with app.app_context():
            db.session.get(User, ids["fern"]).assigned_teacher = None
            db.session.commit()
    client = sign_in(app, actor) if actor else app.test_client()
    path = path.format(**ids)
    form = {}
    if method == "POST":
        dashboard = "/dashboard/" + {"atlas": "admin", "birch": "teacher", "dahlia": "student"}[actor]
        form = {"csrf_token": token(client.get(dashboard))}
        if action in {Action.CREATE_RECORD, Action.EDIT_RECORD}:
            form.update(course="Acceptance course", marks="79")
        elif action == Action.MANAGE_USERS:
            form.update(account_fields(ids, username="elm", role_id=ids["Teacher"], assigned_teacher_id=0))
    response = client.open(path, method=method, data=form)
    assert response.status_code == expected
    if expected == 403:
        assert b"Access restricted" in response.data
    if actor is None:
        assert urlsplit(response.location).path == "/login"
    if expected == 200:
        assert b"Applied Mathematics" in response.data
        assert (b"Earth Science" in response.data) == (actor == "atlas")

    with app.app_context():
        entry = db.session.scalar(db.select(AccessLog).order_by(AccessLog.id.desc()).limit(1))
        assert (entry.actor_user_id, entry.action, entry.resource, entry.decision) == (
            ids.get(actor), action, resource.format(**ids), "Allowed" if expected in {200, 303} else "Denied",
        )
        assert entry.timestamp.utcoffset().total_seconds() == 0

        if action == Action.DELETE_RECORD:
            assert (db.session.get(StudentRecord, ids["first"]) is None) == (expected == 303)
        elif action == Action.CREATE_RECORD:
            record = db.session.get(User, ids["elm"]).student_record
            assert (record.course, record.marks) == ("Acceptance course", 79)
        elif action == Action.EDIT_RECORD:
            record = db.session.get(StudentRecord, ids["first"])
            assert (record.course, record.marks) == ("Applied Mathematics", 82)
        elif method == "POST" and action == Action.MANAGE_USERS:
            assert not is_allowed(ids["birch"], Action.ASSIGN_ROLES)
            assert db.session.get(User, ids["elm"]).role.name == "Student"
