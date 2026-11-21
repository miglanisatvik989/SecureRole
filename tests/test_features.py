import re
from html import unescape

import pytest

from app import create_app
from app.models import AccessLog, Role, StudentRecord, User, db
from app.rbac import Action


PASSWORD = "fictional-demo-password"


@pytest.fixture
def demo(tmp_path):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-fixture-key",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'features.db'}",
    })
    with app.app_context():
        db.create_all()
        roles = {name: Role(name=name) for name in ("Admin", "Teacher", "Student")}
        template = User()
        template.set_password(PASSWORD)

        def account(username, role, teacher=None):
            return User(username=username, display_name=username.title(), role=roles[role],
                        password_hash=template.password_hash, assigned_teacher=teacher)

        admin = account("atlas", "Admin")
        teacher = account("birch", "Teacher")
        other_teacher = account("cedar", "Teacher")
        student = account("dahlia", "Student", teacher)
        missing = account("elm", "Student", teacher)
        other = account("fern", "Student", other_teacher)
        unassigned = account("grove", "Student")
        db.session.add_all((admin, teacher, other_teacher, student, missing, other, unassigned))
        first = StudentRecord(student=student, course="Applied Mathematics", marks=82)
        second = StudentRecord(student=other, course="Earth Science", marks=91)
        db.session.add_all((first, second))
        db.session.commit()
        ids = {user.username: user.id for user in (admin, teacher, other_teacher, student, missing, other, unassigned)}
        ids.update({role.name: role.id for role in roles.values()})
        ids.update(first=first.id, second=second.id)
    yield app, ids
    with app.app_context():
        db.engine.dispose()


def token(response):
    match = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', response.data)
    assert match, response.status_code
    return match.group(1).decode()


def sign_in(app, username, password=PASSWORD):
    client = app.test_client()
    response = submit(client, "/login", username=username, password=password)
    assert response.status_code == 303
    return client


def submit(client, path, **fields):
    return client.post(path, data={"csrf_token": token(client.get(path)), **fields})


def events(action):
    return db.session.scalars(db.select(AccessLog).where(AccessLog.action == action)
                              .order_by(AccessLog.id)).all()


def metric(body, label, value):
    assert re.search(fr"<dt>{label}</dt>\s*<dd[^>]*>{value}</dd>".encode(), body)


def test_dashboard_metrics_and_record_privacy(demo):
    app, ids = demo
    admin = sign_in(app, "atlas")
    assert admin.get("/dashboard/teacher").status_code == 403
    dashboard = admin.get("/dashboard/admin").data
    for label, value in (("Total students", 4), ("Total teachers", 2), ("Academic records", 2),
                         ("Allowed decisions", 1), ("Denied decisions", 1)):
        metric(dashboard, label, value)
    assert b"Applied Mathematics" in dashboard and b"Earth Science" in dashboard
    teacher = sign_in(app, "birch")
    dashboard = teacher.get("/dashboard/teacher").data
    for label, value in (("Assigned students", 2), ("With records", 1), ("Awaiting records", 1)):
        metric(dashboard, label, value)
    assert b"Dahlia" in dashboard and b"Elm" in dashboard
    assert b"Earth Science" not in dashboard and b"Fern" not in dashboard
    assert teacher.get("/records").status_code == 403
    assert teacher.get(f"/records/{ids['second']}").status_code == 403
    student = sign_in(app, "dahlia")
    dashboard = student.get("/dashboard/student").data
    assert b"Applied Mathematics" in dashboard and b"Birch" in dashboard and b"82.0" in dashboard
    assert b"Earth Science" not in dashboard
    assert student.get(f"/records/{ids['first']}").status_code == 200
    assert student.get(f"/records/{ids['second']}").status_code == 403
    assert b"No academic record yet" in sign_in(app, "elm").get("/dashboard/student").data


def test_admin_record_lifecycle(demo):
    app, ids = demo
    client = sign_in(app, "atlas")
    picker = client.get("/records/new").data
    assert b"Add record for Elm" in picker and b"Add record for Dahlia" not in picker
    path = f"/students/{ids['elm']}/record/new"
    assert submit(client, path, course=" Software Engineering ", marks="0").status_code == 303
    assert b"Academic record created." in client.get("/records").data
    with app.app_context():
        record = db.session.scalar(db.select(StudentRecord).filter_by(student_user_id=ids["elm"]))
        record_id = record.id
        assert (record.course, record.marks) == ("Software Engineering", 0)
    base = f"/records/{record_id}"
    assert b"Software Engineering" in client.get(base).data
    assert submit(client, base + "/edit", course="Software Design", marks="94.5").status_code == 303
    assert b"Software Design" in client.get(base).data
    assert b"permanently" in client.get(base + "/delete").data
    assert client.post(base + "/delete", data={}).status_code == 400
    assert submit(client, base + "/delete").status_code == 303
    assert client.get(base).status_code == 403
    with app.app_context():
        assert db.session.get(StudentRecord, record_id) is None
        # The delete confirmation page was opened twice. A failed CSRF check adds no entry.
        for action, count in ((Action.CREATE_RECORD, 2), (Action.EDIT_RECORD, 2), (Action.DELETE_RECORD, 3)):
            assert [entry.decision for entry in events(action)] == ["Allowed"] * count


def test_teacher_scope_and_student_write_denials(demo):
    app, ids = demo
    teacher = sign_in(app, "birch")
    create = f"/students/{ids['elm']}/record/new"
    edit = f"/records/{ids['first']}/edit"
    delete = f"/records/{ids['first']}/delete"
    csrf = token(teacher.get(create))
    assert teacher.post(create, data={"csrf_token": csrf, "course": "Data Systems", "marks": 76}).status_code == 303
    assert submit(teacher, edit, course="Calculus", marks=88).status_code == 303
    assert teacher.post(delete, data={"csrf_token": csrf}).status_code == 403
    for student in ("fern", "grove"):
        assert teacher.post(f"/students/{ids[student]}/record/new", data={
            "csrf_token": csrf, "course": "Forbidden", "marks": 70,
        }).status_code == 403
    assert teacher.post(f"/records/{ids['second']}/edit", data={
        "csrf_token": csrf, "course": "Forbidden", "marks": 70,
    }).status_code == 403
    student = sign_in(app, "dahlia")
    student_csrf = token(student.get("/dashboard/student"))
    assert student.post(edit, data={"csrf_token": student_csrf, "course": "Forbidden", "marks": 70}).status_code == 403
    with app.app_context():
        assert db.session.get(StudentRecord, ids["first"]).course == "Calculus"
        assert [entry.decision for entry in events(Action.DELETE_RECORD)] == ["Denied"]


@pytest.mark.parametrize("course,marks", [("  ", "20"), ("Valid", "101"), ("Valid", "NaN"), ("Valid", "-1")])
def test_failed_validation_has_no_successful_mutation_audit(demo, course, marks):
    app, ids = demo
    client = sign_in(app, "birch")
    path = f"/students/{ids['elm']}/record/new"
    csrf = token(client.get("/dashboard/teacher"))
    response = client.post(path, data={"csrf_token": csrf, "course": course, "marks": marks})
    assert response.status_code == 400
    assert b'aria-invalid="true"' in response.data
    with app.app_context():
        assert db.session.get(User, ids["elm"]).student_record is None
        assert not events(Action.CREATE_RECORD)


def test_duplicate_record_rolls_back_audit(demo):
    app, ids = demo
    client = sign_in(app, "atlas")
    csrf = token(client.get("/dashboard/admin"))
    response = client.post(f"/students/{ids['dahlia']}/record/new", data={
        "csrf_token": csrf, "course": "Duplicate", "marks": 20,
    })
    assert b"already has an academic record" in response.data
    assert response.status_code == 400
    with app.app_context():
        assert not events(Action.CREATE_RECORD)
        assert db.session.get(StudentRecord, ids["first"]).course == "Applied Mathematics"


def account_fields(ids, **changes):
    return dict(dict(username="iris", display_name="Iris", email="iris@example.test",
                     role_id=ids["Student"], assigned_teacher_id=ids["birch"]), **changes)


def test_account_creation_profile_edits_roles_and_password_reset(demo):
    app, ids = demo
    client = sign_in(app, "atlas")
    initial = "fictional-initial-password"
    replacement = "fictional-replacement-password"
    assert submit(client, "/users/new", **account_fields(ids), password=initial).status_code == 303
    listing = client.get("/users").data
    assert b"iris@example.test" in listing and initial.encode() not in listing
    with app.app_context():
        iris = db.session.scalar(db.select(User).filter_by(username="iris"))
        user_id = iris.id
        assert iris.role.name == "Student" and iris.assigned_teacher_id == ids["birch"]
        assert iris.password_hash != initial and iris.check_password(initial)
    assert submit(client, f"/users/{user_id}/edit", **account_fields(
        ids, display_name="Iris Lane", assigned_teacher_id=ids["cedar"]
    )).status_code == 303
    assert submit(client, f"/users/{user_id}/edit", **account_fields(
        ids, display_name="Iris Lane", role_id=ids["Teacher"], assigned_teacher_id=0,
    )).status_code == 303
    assert submit(client, f"/users/{user_id}/password", password=replacement).status_code == 303
    with app.app_context():
        iris = db.session.get(User, user_id)
        assert (iris.role.name, iris.assigned_teacher_id, iris.display_name) == ("Teacher", None, "Iris Lane")
        assert iris.check_password(replacement) and not iris.check_password(initial)
        assert [entry.decision for entry in events(Action.ASSIGN_ROLES)] == ["Allowed", "Allowed"]
        assert [entry.decision for entry in events(Action.ASSIGN_TEACHERS)] == ["Allowed"] * 3
    assert sign_in(app, "iris", replacement).get("/dashboard/teacher").status_code == 200


def test_user_constraints_and_last_admin(demo):
    app, ids = demo
    client = sign_in(app, "atlas")
    csrf = token(client.get("/dashboard/admin"))

    def post(path, **fields):
        return client.post(path, data={"csrf_token": csrf, **fields})

    def edit(user, **changes):
        return post(f"/users/{ids[user]}/edit", **account_fields(ids, username=user, **changes))

    duplicate = post("/users/new", **account_fields(ids, username="dahlia"), password=PASSWORD)
    assert duplicate.status_code == 409
    assert b"conflicts with existing data" in duplicate.data
    assert post("/users/new", **account_fields(ids, assigned_teacher_id=ids["atlas"]), password=PASSWORD).status_code == 400
    assert b"retain the Admin role" in edit("atlas", role_id=ids["Teacher"], assigned_teacher_id=0).data
    assert b"academic record before changing" in edit("dahlia", role_id=ids["Teacher"], assigned_teacher_id=0).data
    assert b"Reassign this teacher" in edit("birch", assigned_teacher_id=0).data
    with app.app_context():
        assert db.session.get(User, ids["atlas"]).role.name == "Admin"
        assert db.session.get(User, ids["dahlia"]).role.name == "Student"
        assert not events(Action.MANAGE_USERS)
        assert not events(Action.ASSIGN_ROLES)
        assert not events(Action.ASSIGN_TEACHERS)


def test_admin_pages_deny_non_admin(demo):
    app, ids = demo
    client = sign_in(app, "birch")
    for target in ("/users", "/users/new", f"/users/{ids['atlas']}/edit",
                   f"/users/{ids['atlas']}/password", "/access-logs"):
        assert client.get(target).status_code == 403
    csrf = token(client.get("/dashboard/teacher"))
    assert client.post(f"/users/{ids['atlas']}/password", data={
        "csrf_token": csrf, "password": "fictional-replacement-password",
    }).status_code == 403


def test_access_log_filters_pagination_and_audit_snapshots(demo):
    app, ids = demo
    with app.app_context():
        for index in range(25):
            db.session.add(AccessLog(actor_user_id=None, action="record.view",
                                     resource=f"unique-log-{index:02}", decision="Denied"))
        db.session.add(AccessLog(actor_user_id=ids["birch"], action="record.edit",
                                 resource="unique-edit", decision="Allowed"))
        db.session.commit()
    client = sign_in(app, "atlas")
    response = client.get("/access-logs", query_string={"decision": "Denied", "action": "record.view", "q": "unique-log"})
    assert response.status_code == 200
    body = response.text
    assert "25 results · Page 1 of 2" in body
    assert "Anonymous" in body and "unique-edit" not in body
    assert body.index("unique-log-24") < body.index("unique-log-23") and "unique-log-00" not in body
    next_url = unescape(re.search(r'rel="next" href="([^"]+)"', body).group(1))
    page_two = client.get(next_url).text
    assert "25 results · Page 2 of 2" in page_two and "unique-log-00" in page_two
    assert "unique-log-24" not in page_two
    filtered = client.get("/access-logs", query_string={"q": "BIRCH", "decision": "Allowed"}).text
    assert "Birch" in filtered and "unique-edit" in filtered
    with app.app_context():
        assert len(events(Action.VIEW_ACCESS_LOGS)) == 3
        assert all(entry.actor_user_id == ids["atlas"] for entry in events(Action.VIEW_ACCESS_LOGS))
