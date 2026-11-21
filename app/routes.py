"""Dashboard placeholders and role-based navigation."""

from flask import Blueprint, abort, current_app, make_response, redirect, render_template, url_for
from flask_login import current_user

from sqlalchemy.orm import joinedload

from app.activity import recent_activity
from app.models import AccessLog, Role, StudentRecord, User, db
from app.records import record_rows
from app.workspace import render_workspace
from app.rbac import Action, require_permission, scoped_students

main = Blueprint("main", __name__)

DASHBOARD_ROLES = {"admin": "Admin", "teacher": "Teacher", "student": "Student"}


def dashboard_url(user):
    return url_for("main.role_dashboard", role=user.role.name.lower())


@main.get("/")
def index():
    if current_user.is_authenticated:
        return redirect(dashboard_url(current_user))
    return redirect(url_for("auth.login"))


@main.get("/dashboard")
def dashboard():
    require_permission(Action.VIEW_DASHBOARD)
    return redirect(dashboard_url(current_user))


@main.get("/dashboard/<role>")
def role_dashboard(role):
    if role not in DASHBOARD_ROLES:
        if not current_user.is_authenticated:
            return current_app.login_manager.unauthorized()
        abort(404)
    require_permission(Action.VIEW_DASHBOARD, dashboard_role=DASHBOARD_ROLES[role])
    if role == "admin":
        roles = dict(db.session.execute(db.select(Role.name, db.func.count(User.id))
                                       .join(User, User.role_id == Role.id).group_by(Role.name)).all())
        decisions = dict(db.session.execute(db.select(AccessLog.decision, db.func.count(AccessLog.id))
                                           .group_by(AccessLog.decision)).all())
        record_count = db.session.scalar(db.select(db.func.count(StudentRecord.id)))
        metrics = [("Total students", roles.get("Student", 0)), ("Total teachers", roles.get("Teacher", 0)),
                   ("Academic records", record_count), ("Allowed decisions", decisions.get("Allowed", 0)),
                   ("Denied decisions", decisions.get("Denied", 0))]
        return render_workspace("dashboards/admin.html", metrics=metrics, rows=record_rows(limit=5),
                                logs=recent_activity(), active="dashboard")

    if role == "teacher":
        students = db.session.scalars(scoped_students(current_user.id).options(joinedload(User.student_record))
                                      .order_by(User.display_name, User.id)).all()
        with_records = sum(student.student_record is not None for student in students)
        metrics = [("Assigned students", len(students)), ("With records", with_records),
                   ("Awaiting records", len(students) - with_records)]
        return render_workspace("dashboards/teacher.html", students=students, metrics=metrics, active="dashboard")

    rows = record_rows(limit=1)
    return render_workspace("dashboards/student.html", record=rows[0] if rows else None, active="dashboard")


def access_restricted(error):
    response = make_response(render_template("403.html"), 403)
    response.cache_control.no_store = True
    return response
