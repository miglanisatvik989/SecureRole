"""Sign in with a stored account and sign out with a protected form."""

from flask import Blueprint, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf.csrf import CSRFError
from werkzeug.security import check_password_hash, generate_password_hash

from app.forms import LoginForm, LogoutForm
from app.models import User, db
from app.routes import dashboard_url
from app.session_security import bind_session

auth = Blueprint("auth", __name__)

# Run the same password hashing work when the username does not exist.
_missing_user_hash = generate_password_hash("unused authentication placeholder")


@auth.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(dashboard_url(current_user))

    form = LoginForm()
    error = None
    status = 200
    if form.validate_on_submit():
        user = db.session.scalar(db.select(User).filter_by(username=form.username.data))
        if user is None:
            check_password_hash(_missing_user_hash, form.password.data)
        elif user.check_password(form.password.data):
            session.clear()
            login_user(user)
            bind_session(user)
            destination = dashboard_url(user)
            # Only the app-generated dashboard paths are accepted as return targets.
            if request.args.get("next") == url_for("main.dashboard"):
                destination = url_for("main.dashboard")
            return redirect(destination, code=303)
        error = "Invalid username or password."
        status = 401
    elif request.method == "POST":
        status = 400
    return render_template("login.html", form=form, error=error), status


@auth.post("/logout")
@login_required
def logout():
    if not LogoutForm().validate_on_submit():
        raise CSRFError()
    session.clear()
    logout_user()
    return redirect(url_for("auth.login"), code=303)


def handle_csrf_error(error):
    message = "This form expired or could not be verified. Please try again."
    if request.endpoint == "auth.login" and not current_user.is_authenticated:
        return render_template("login.html", form=LoginForm(formdata=None), error=message), 400
    return render_template("csrf_error.html", message=message), 400
