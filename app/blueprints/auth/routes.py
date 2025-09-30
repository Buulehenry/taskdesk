# app/blueprints/auth/routes.py
from datetime import datetime
from typing import Optional

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from ...services.email_service import send_email
from ...extensions import db
from ...models.user import User, ClientProfile, FreelancerProfile
from ...models.fileasset import FileAsset
from . import auth_bp
from .forms import RegisterForm, LoginForm, ForgotPasswordForm, ResetPasswordForm

# -----------------
# Utilities
# -----------------

def _ts() -> URLSafeTimedSerializer:
    secret_key = current_app.config.get("SECRET_KEY")
    salt = current_app.config.get("SECURITY_PASSWORD_SALT", "pwd-reset")
    return URLSafeTimedSerializer(secret_key=secret_key, salt=salt)


def _issue_reset_token(user_id: int) -> str:
    return _ts().dumps({"uid": user_id, "ts": datetime.utcnow().isoformat()})


def _verify_reset_token(token: str, max_age: int = 60 * 60 * 24) -> Optional[int]:
    try:
        data = _ts().loads(token, max_age=max_age)
        return int(data.get("uid"))
    except (BadSignature, SignatureExpired, ValueError, TypeError):
        return None


def _redirect_next(default_endpoint: str):
    nxt = request.args.get("next") or request.form.get("next")
    return nxt if nxt else url_for(default_endpoint)


# Optional: swap this with your actual email service

def send_password_reset_email(user: User, link: str):
    send_email(
        to=user.email,
        subject="Reset your TaskDesk password",
        template="password_reset.html",
        user=user,
        link=link,
    )

# -----------------
# Register
# -----------------

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('client.dashboard'))

    form = RegisterForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        role = form.role.data.strip() if form.role.data in ("client", "freelancer") else "client"

        # Uniqueness is checked in form validator too, but double check to be safe
        if User.query.filter_by(email=email).first():
            flash('Email is already registered. Try logging in.', 'warning')
            return redirect(url_for('auth.login'))

        user = User(
            name=form.name.data.strip(),
            email=email,
            phone=(form.phone.data or '').strip(),
            role=role,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.flush()  # get user.id

        # Create 1:1 profile
        prof = ClientProfile(user_id=user.id) if role == 'client' else FreelancerProfile(user_id=user.id)
        db.session.add(prof)

        db.session.commit()
        flash('Account created. You can now log in.', 'success')
        return redirect(url_for('auth.login'))

    # Pre-select role if provided as query param
    preselect_role = request.args.get('role')
    if preselect_role in ("client", "freelancer"):
        form.role.data = preselect_role

    return render_template('auth/register.html', form=form)


# -----------------
# Login / Logout
# -----------------

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('client.dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(form.password.data):
            flash('Invalid email or password.', 'danger')
            return render_template('auth/login.html', form=form)

        if user.status == 'suspended':
            flash('Your account is suspended. Contact support.', 'warning')
            return render_template('auth/login.html', form=form)

        if user.deleted_at is not None:
            flash('This account was deleted.', 'warning')
            return render_template('auth/login.html', form=form)

        login_user(user, remember=bool(form.remember.data))
        # Optional: update last login signal if present
        if hasattr(user, 'mark_login'):
            user.mark_login()
        db.session.commit()

        # Route by role (optional)
        if user.role == 'freelancer':
            return redirect(_redirect_next('freelancer.dashboard'))
        elif user.role == 'admin':
            return redirect(_redirect_next('admin.dashboard'))
        else:
            return redirect(_redirect_next('client.dashboard'))

    # Preserve next param
    form.next.data = request.args.get('next', '')
    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


# -----------------
# Forgot / Reset Password
# -----------------

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email).first()
        # mask whether email exists
        if user:
            token = _issue_reset_token(user.id)
            link = url_for('auth.reset_password', token=token, _external=True)
            send_password_reset_email(user, link)
        flash('If that email is registered, you will receive a reset link shortly.', 'info')
        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html', form=form)


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user_id = _verify_reset_token(token)
    if not user_id:
        flash('The reset link is invalid or has expired.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    user = User.query.get_or_404(user_id)
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash('Your password has been reset. Please sign in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', form=form)


# -----------------
# (Optional) Email Verification Hooks
# -----------------

@auth_bp.route('/verify/<token>')
def verify_email(token):
    # Optional – only if you send verification emails
    user_id = _verify_reset_token(token, max_age=60 * 60 * 24 * 3)
    if not user_id:
        flash('Verification link invalid or expired.', 'danger')
        return redirect(url_for('auth.login'))

    user = User.query.get_or_404(user_id)
    user.is_email_verified = True
    db.session.commit()
    flash('Email verified successfully.', 'success')
    return redirect(url_for('auth.login'))
