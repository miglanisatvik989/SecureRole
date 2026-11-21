"""Phase 4 dashboard placeholders and role-based navigation."""

from flask import Blueprint, abort, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.forms import LogoutForm

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
@login_required
def dashboard():
    return redirect(dashboard_url(current_user))


@main.get("/dashboard/<role>")
@login_required
def role_dashboard(role):
    if role not in DASHBOARD_ROLES:
        abort(404)
    if current_user.role.name != DASHBOARD_ROLES[role]:
        abort(403)
    return render_template("dashboard.html", logout_form=LogoutForm())
