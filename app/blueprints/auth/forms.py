# app/blueprints/auth/forms.py
from __future__ import annotations
from typing import Optional

from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    PasswordField,
    SubmitField,
    BooleanField,
    HiddenField,
    SelectField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    Length,
    EqualTo,
    Optional as Opt,
    Regexp,
)

# Lazy import to avoid circulars in type checkers / runtime
try:
    from ...models.user import User
    from ...extensions import db
except Exception:  # pragma: no cover
    User = None  # type: ignore
    db = None  # type: ignore


# ---------------------
# Validators / Helpers
# ---------------------

PASSWORD_VALIDATORS = [
    DataRequired(),
    Length(min=8, message="Password must be at least 8 characters."),
    # Optional extra strength: at least one letter and number
    Regexp(r"^(?=.*[A-Za-z])(?=.*\d).+$", message="Use letters and numbers."),
]


def _email_exists(email: str) -> bool:
    if not User:
        return False
    return User.query.filter(User.email == email.lower().strip()).first() is not None


# -------------
# Auth Forms
# -------------

class RegisterForm(FlaskForm):
    name = StringField("Full name", validators=[DataRequired(), Length(max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    phone = StringField("Phone", validators=[Opt(), Length(max=50)])
    role = SelectField(
        "Account type",
        choices=[("client", "Client"), ("freelancer", "Freelancer")],
        validators=[DataRequired()],
        default="client",
    )
    password = PasswordField("Password", validators=PASSWORD_VALIDATORS)
    password2 = PasswordField("Confirm password", validators=[DataRequired(), EqualTo("password", message="Passwords must match.")])
    submit = SubmitField("Create account")

    next = HiddenField()

    def validate_email(self, field):  # type: ignore[override]
        if _email_exists(field.data):
            raise ValueError("This email is already registered.")


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Keep me signed in")
    submit = SubmitField("Sign in")

    next = HiddenField()


class ForgotPasswordForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    submit = SubmitField("Send reset link")


class ResetPasswordForm(FlaskForm):
    password = PasswordField("New password", validators=PASSWORD_VALIDATORS)
    password2 = PasswordField("Confirm new password", validators=[DataRequired(), EqualTo("password", message="Passwords must match.")])
    submit = SubmitField("Reset password")


# (Optional) Change password for logged-in users
class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current password", validators=[DataRequired()])
    password = PasswordField("New password", validators=PASSWORD_VALIDATORS)
    password2 = PasswordField("Confirm new password", validators=[DataRequired(), EqualTo("password")])
    submit = SubmitField("Update password")
