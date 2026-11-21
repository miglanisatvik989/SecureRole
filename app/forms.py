"""Forms shared by the authentication and dashboard views."""

from math import isfinite

from flask_wtf import FlaskForm
from wtforms import FloatField, PasswordField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, InputRequired, Length, NumberRange, Optional, Regexp, ValidationError


def stripped(value):
    return value.strip() if value else value


def printable(form, field):
    if field.data and not field.data.isprintable():
        raise ValidationError("Use printable characters only.")


def nonblank_password(form, field):
    if not field.data.strip():
        raise ValidationError("Choose a password that contains a non-whitespace character.")


class LoginForm(FlaskForm):
    username = StringField("Username", filters=[stripped],
                           validators=[DataRequired(message="Enter your username."), Length(max=80), printable])
    password = PasswordField("Password", validators=[InputRequired(message="Enter your password."), Length(max=128)])
    submit = SubmitField("Sign in")


class LogoutForm(FlaskForm):
    submit = SubmitField("Sign out")


class RecordForm(FlaskForm):
    course = StringField("Course", filters=[stripped], validators=[DataRequired(), Length(max=100), printable])
    marks = FloatField("Marks (out of 100)", validators=[InputRequired(), NumberRange(min=0, max=100)])
    submit = SubmitField("Save record")

    def validate_marks(self, field):
        if field.data is not None and not isfinite(field.data):
            raise ValidationError("Enter a finite mark between 0 and 100.")


class DeleteRecordForm(FlaskForm):
    submit = SubmitField("Delete record")


class AccountForm(FlaskForm):
    username = StringField("Username", filters=[stripped], validators=[DataRequired(), Length(max=80), printable])
    display_name = StringField("Display name", filters=[stripped], validators=[DataRequired(), Length(max=100), printable])
    email = StringField("Email (optional)", filters=[stripped], validators=[
        Optional(), Length(max=120), printable, Regexp(r"[^@\s]+@[^@\s]+\.[^@\s]+\Z", message="Enter a valid email address.")
    ])
    role_id = SelectField("Role", coerce=int)
    assigned_teacher_id = SelectField("Assigned teacher", coerce=int)
    submit = SubmitField("Save account")


class NewAccountForm(AccountForm):
    password = PasswordField("Initial password", validators=[InputRequired(), Length(min=12, max=128), nonblank_password])


class ResetPasswordForm(FlaskForm):
    password = PasswordField("New password", validators=[InputRequired(), Length(min=12, max=128), nonblank_password])
    submit = SubmitField("Reset password")
