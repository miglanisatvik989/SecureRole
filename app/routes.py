"""Dashboard placeholders and role-based navigation."""

from flask import Blueprint, abort, current_app, make_response, redirect, render_template, url_for
from flask_login import current_user

from app.forms import LogoutForm
from app.rbac import Action, require_permission

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
    return render_template("dashboard.html", logout_form=LogoutForm())


def access_restricted(error):
    response = make_response(render_template("403.html"), 403)
    response.cache_control.no_store = True
    return response
