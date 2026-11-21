"""Administrator account management without account deletion."""

from flask import Blueprint, abort, flash, redirect, request, url_for
from flask_login import current_user
from sqlalchemy.orm import joinedload

from app.forms import AccountForm, NewAccountForm, ResetPasswordForm
from app.models import Role, User, db
from app.rbac import Action, require_permission
from app.workspace import render_workspace, save_changes

accounts = Blueprint("accounts", __name__)


def user_by_id(user_id):
    if user_id > 2**63 - 1:
        abort(404)
    user = db.session.get(User, user_id, populate_existing=True)
    if user is None:
        abort(404)
    return user


def configure_choices(form):
    roles = db.session.scalars(db.select(Role).order_by(Role.name)).all()
    teachers = db.session.scalars(db.select(User).join(User.role).where(Role.name == "Teacher")
                                  .order_by(User.display_name, User.id)).all()
    form.role_id.choices = [(role.id, role.name) for role in roles]
    form.assigned_teacher_id.choices = [(0, "Unassigned")] + [
        (teacher.id, f"{teacher.display_name} (@{teacher.username})") for teacher in teachers
    ]


@accounts.get("/users")
def index():
    require_permission(Action.MANAGE_USERS)
    rows = db.session.scalars(db.select(User).options(joinedload(User.role), joinedload(User.assigned_teacher))
                              .order_by(User.display_name, User.id)).all()
    return render_workspace("accounts/list.html", rows=rows, active="users")


@accounts.route("/users/new", methods=["GET", "POST"])
@accounts.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
def edit(user_id=None):
    creating = user_id is None
    form_class = NewAccountForm if creating else AccountForm
    error, status = None, 200
    if request.method == "GET":
        require_permission(Action.MANAGE_USERS)
        user = None if creating else user_by_id(user_id)
        form = form_class(obj=user)
        if user and user.assigned_teacher_id is None:
            form.assigned_teacher_id.data = 0
        configure_choices(form)
    else:
        form = form_class()
        validated = False

        def change():
            nonlocal validated
            require_permission(Action.MANAGE_USERS, atomic=True)
            configure_choices(form)
            if not form.validate():
                raise ValueError("Review the highlighted fields.")
            validated = True
            user = User() if creating else user_by_id(user_id)
            role = db.session.get(Role, form.role_id.data)
            teacher_id = form.assigned_teacher_id.data or None

            if user.role_id != role.id:
                require_permission(Action.ASSIGN_ROLES, atomic=True)
            if user.assigned_teacher_id != teacher_id:
                require_permission(Action.ASSIGN_TEACHERS, atomic=True)
            if role.name != "Student" and teacher_id is not None:
                raise ValueError("Only Student accounts can have an assigned teacher.")
            if not creating and user.role.name == "Admin" and role.name != "Admin":
                administrators = db.session.scalar(db.select(db.func.count(User.id)).filter_by(role_id=user.role_id))
                if administrators <= 1:
                    raise ValueError("At least one account must retain the Admin role.")
            if not creating and role.name != "Student" and user.student_record is not None:
                raise ValueError("Remove this student's academic record before changing their role.")
            if not creating and role.name != "Teacher" and user.assigned_students:
                raise ValueError("Reassign this teacher's students before changing their role.")

            user.username = form.username.data
            user.display_name = form.display_name.data
            user.email = form.email.data or None
            user.role = role
            user.assigned_teacher_id = teacher_id
            if creating:
                user.set_password(form.password.data)
                db.session.add(user)

        error, status = save_changes(change)
        if error is None:
            flash("Account created." if creating else "Account updated.", "success")
            return redirect(url_for("main.dashboard") if user_id == current_user.id else url_for("accounts.index"),
                            code=303)
        if status >= 500 and not validated:
            # An error may occur before the transaction reaches the authorization guard.
            require_permission(Action.MANAGE_USERS, atomic=True)
            db.session.rollback()
            configure_choices(form)

    fields = [form.display_name, form.username, form.email, form.role_id, form.assigned_teacher_id]
    if creating:
        fields.append(form.password)
    return render_workspace("workspace_form.html", title="Create account" if creating else "Edit account",
                            form=form, fields=fields, error=error, status=status, active="users",
                            cancel=url_for("accounts.index"))


@accounts.route("/users/<int:user_id>/password", methods=["GET", "POST"])
def reset_password(user_id):
    form = ResetPasswordForm()
    error, status = None, 200
    if form.validate_on_submit():
        def change():
            require_permission(Action.MANAGE_USERS, atomic=True)
            user_by_id(user_id).set_password(form.password.data)

        error, status = save_changes(change)
        if error is None:
            flash("Password reset.", "success")
            return redirect(url_for("accounts.index"), code=303)
    if request.method == "GET":
        require_permission(Action.MANAGE_USERS)
    else:
        require_permission(Action.MANAGE_USERS, atomic=True)
        db.session.rollback()
        status = status if error else 400
    user = user_by_id(user_id)
    return render_workspace("workspace_form.html", title="Reset password", subject=user.display_name, form=form,
                            fields=(form.password,), error=error, status=status, active="users",
                            cancel=url_for("accounts.index"))
