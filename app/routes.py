"""Role dashboards and shared navigation."""

from flask import Blueprint, abort, current_app, make_response, redirect, render_template, url_for
from flask_login import current_user


from app.activity import recent_activity
from app.listing import student_listing
from app.models import AccessLog, Role, StudentRecord, User, db
from app.records import record_rows
from app.workspace import render_workspace
from app.rbac import Action, permission_scope, require_permission, scoped_students

main = Blueprint("main", __name__)

DASHBOARD_ROLES = {"admin": "Admin", "teacher": "Teacher", "student": "Student"}


PERMISSION_LABELS = (
    ("View records", Action.VIEW_RECORD), ("Add records", Action.CREATE_RECORD),
    ("Edit records", Action.EDIT_RECORD), ("Delete records", Action.DELETE_RECORD),
    ("Manage users", Action.MANAGE_USERS), ("Assign roles", Action.ASSIGN_ROLES),
    ("View audit logs", Action.VIEW_ACCESS_LOGS),
)


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
    permissions = []
    for label, action in PERMISSION_LABELS:
        scope = permission_scope(DASHBOARD_ROLES[role], action)
        permissions.append((label, "allowed" if action == Action.DELETE_RECORD and scope == "all" else scope))
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
                                logs=recent_activity(), permissions=permissions, active="dashboard")

    if role == "teacher":
        scope = scoped_students(current_user.id)
        assigned = db.session.scalar(db.select(db.func.count()).select_from(scope.subquery()))
        with_records = db.session.scalar(db.select(db.func.count()).select_from(
            scope.where(User.student_record.has()).subquery()
        ))
        metrics = [("Assigned students", assigned), ("With records", with_records),
                   ("Awaiting records", assigned - with_records)]
        return render_workspace("dashboards/teacher.html", listing=student_listing(scope), metrics=metrics,
                                assigned=assigned, permissions=permissions, active="dashboard")

    rows = record_rows(limit=1)
    return render_workspace("dashboards/student.html", record=rows[0] if rows else None,
                            permissions=permissions, active="dashboard")


def access_restricted(error):
    response = make_response(render_template("403.html"), 403)
    response.cache_control.no_store = True
    return response
