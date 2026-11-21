"""Forms shared by the authentication and dashboard views."""

from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, InputRequired


class LoginForm(FlaskForm):
    username = StringField("Username", filters=[lambda value: value.strip() if value else value],
                           validators=[DataRequired(message="Enter your username.")])
    password = PasswordField("Password", validators=[InputRequired(message="Enter your password.")])
    submit = SubmitField("Sign in")


class LogoutForm(FlaskForm):
    submit = SubmitField("Sign out")
