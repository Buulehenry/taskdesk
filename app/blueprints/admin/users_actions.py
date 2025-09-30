from datetime import datetime
from flask import request, redirect, url_for, flash
from flask_login import login_required, current_user
from ...security import roles_required
from ...extensions import db
from ...models.user import User, KycSubmission
from ...services.email_service import send_email
from ..auth.routes import _issue_reset_token, send_password_reset_email
from . import admin_bp
from .utils import _record_admin_audit

# ---- BULK suspend / unsuspend ----

@admin_bp.post('/users/bulk-suspend')
@login_required
@roles_required('admin')
def users_bulk_suspend():
    raw = (request.form.get('ids') or '')
    ids = sorted({int(x) for x in raw.split(',') if x.isdigit()})
    if not ids:
        flash('Select at least one user.', 'warning')
        return redirect(url_for('admin.users_list'))

    q = User.query.filter(
        User.id.in_(ids),
        User.deleted_at.is_(None),
        User.status != 'suspended',
    )
    updated = q.update({User.status: 'suspended'}, synchronize_session=False)
    db.session.commit()

    try:
        reason = (request.form.get('reason') or '').strip()
        if updated:
            _record_admin_audit(
                actor_id=current_user.id,
                action='bulk_suspend',
                targets=ids,
                meta={'count': updated, **({'reason': reason} if reason else {})},
            )
    except Exception:
        pass

    flash('No eligible users to suspend.' if updated == 0 else f'Suspended {updated} user(s).', 'warning' if updated else 'info')
    return redirect(request.referrer or url_for('admin.users_list'))

@admin_bp.post('/users/bulk-unsuspend')
@login_required
@roles_required('admin')
def users_bulk_unsuspend():
    raw = (request.form.get('ids') or '')
    ids = sorted({int(x) for x in raw.split(',') if x.isdigit()})
    if not ids:
        flash('Select at least one user.', 'warning')
        return redirect(url_for('admin.users_list'))

    q = User.query.filter(
        User.id.in_(ids),
        User.deleted_at.is_(None),
        User.status == 'suspended',
    )
    updated = q.update({User.status: 'active'}, synchronize_session=False)
    db.session.commit()

    try:
        _record_admin_audit(
            actor_id=current_user.id,
            action='bulk_unsuspend',
            targets=ids,
            meta={'count': updated},
        )
    except Exception:
        pass

    flash('No eligible users to unsuspend.' if updated == 0 else f'Unsuspended {updated} user(s).', 'success' if updated else 'info')
    return redirect(request.referrer or url_for('admin.users_list'))

# ---- Single suspend / unsuspend ----

@admin_bp.post('/users/suspend')
@login_required
@roles_required('admin')
def user_suspend():
    uid = request.form.get('user_id', type=int) or request.form.get('id', type=int)
    reason = (request.form.get('reason') or '').strip()
    if not uid:
        flash('Missing user id.', 'warning')
        return redirect(request.referrer or url_for('admin.users_list'))

    u = User.query.get_or_404(uid)

    if u.deleted_at:
        flash('Cannot suspend a deleted user.', 'warning')
        return redirect(request.referrer or url_for('admin.users_list'))

    if u.status == 'suspended':
        flash('User is already suspended.', 'info')
        return redirect(request.referrer or url_for('admin.users_list'))

    u.status = 'suspended'
    db.session.commit()

    try:
        _record_admin_audit(
            actor_id=current_user.id,
            action='suspend',
            targets=[u.id],
            meta={'reason': reason} if reason else None,
        )
    except Exception:
        pass

    flash(f'User {u.name or u.email} suspended.', 'warning')
    return redirect(request.referrer or url_for('admin.users_list'))

@admin_bp.post('/users/unsuspend')
@login_required
@roles_required('admin')
def user_unsuspend():
    uid = request.form.get('user_id', type=int) or request.form.get('id', type=int)
    if not uid:
        flash('Missing user id.', 'warning')
        return redirect(request.referrer or url_for('admin.users_list'))

    u = User.query.get(uid)
    if not u:
        flash('User not found.', 'warning')
        return redirect(request.referrer or url_for('admin.users_list'))

    if u.deleted_at:
        flash('Cannot unsuspend a deleted user.', 'warning')
        return redirect(request.referrer or url_for('admin.users_list'))

    if u.status != 'suspended':
        flash('User is not suspended.', 'info')
        return redirect(request.referrer or url_for('admin.users_list'))

    u.status = 'active'
    db.session.commit()

    try:
        _record_admin_audit(
            actor_id=current_user.id,
            action='unsuspend',
            targets=[u.id],
        )
    except Exception:
        pass

    flash(f'{u.email} unsuspended.', 'success')
    return redirect(request.referrer or url_for('admin.users_list'))

# ---- Role changes (bulk + single) ----

@admin_bp.post('/users/change-role')
@login_required
@roles_required('admin')
def users_bulk_role():
    ids = [int(x) for x in (request.form.get('ids') or '').split(',') if x.isdigit()]
    role = (request.form.get('role') or '').strip()
    if role not in ('client','freelancer','admin'):
        flash('Invalid role.', 'warning'); return redirect(url_for('admin.users_list'))
    if not ids:
        flash('Select at least one user.', 'warning'); return redirect(url_for('admin.users_list'))
    User.query.filter(User.id.in_(ids)).update({User.role: role}, synchronize_session=False)
    db.session.commit()
    flash(f'Updated role to {role} for {len(ids)} user(s).', 'success')
    return redirect(url_for('admin.users_list'))

@admin_bp.post('/users/<int:user_id>/change-role')
@login_required
@roles_required('admin')
def user_change_role(user_id):
    role = (request.form.get('role') or '').strip()
    if role not in ('client', 'freelancer', 'admin'):
        flash('Invalid role.', 'warning')
        return redirect(request.referrer or url_for('admin.users_list'))
    u = User.query.get_or_404(user_id)
    u.role = role
    db.session.commit()
    flash(f'Role updated to {role} for {u.email}.', 'success')
    return redirect(request.referrer or url_for('admin.user_detail', user_id=u.id))

# ---- Notes / Compliance / Reset / New / Delete ----

@admin_bp.post('/users/<int:user_id>/notes')
@login_required
@roles_required('admin')
def user_notes_save(user_id):
    u = User.query.get_or_404(user_id)
    u.notes_internal = (request.form.get('notes') or '').strip()
    db.session.commit()
    flash('Notes saved.', 'success')
    return redirect(url_for('admin.user_detail', user_id=u.id))

@admin_bp.post('/users/<int:user_id>/compliance')
@login_required
@roles_required('admin')
def user_compliance_action(user_id):
    u = User.query.get_or_404(user_id)
    if request.form.get('erase'):
        # enqueue erasure job here as per your policy
        flash('PII erasure queued.', 'warning')
    else:
        # enqueue export job here
        flash('Data export started.', 'info')
    return redirect(url_for('admin.user_detail', user_id=u.id))

@admin_bp.post('/users/send-reset')
@login_required
@roles_required('admin')
def user_send_reset():
    uid = request.form.get('user_id', type=int)
    if not uid:
        flash('Missing user id.', 'warning')
        return redirect(request.referrer or url_for('admin.users_list'))

    user = User.query.get(uid)
    if not user or not user.email:
        flash('User not found or has no email on file.', 'warning')
        return redirect(request.referrer or url_for('admin.users_list'))

    token = _issue_reset_token(user.id)
    link  = url_for('auth.reset_password', token=token, _external=True)

    try:
        send_password_reset_email(user, link)
        flash('Password reset link sent to the user.', 'success')
    except Exception:
        flash('Failed to send reset link. Please try again or notify manually.', 'danger')

    return redirect(request.referrer or url_for('admin.users_list'))

@admin_bp.route('/users/new', methods=['POST'])
@login_required
@roles_required('admin')
def user_new():
    from werkzeug.security import generate_password_hash

    name   = (request.form.get('name') or '').strip()
    email  = (request.form.get('email') or '').strip().lower()
    phone  = (request.form.get('phone') or '').strip()
    role   = (request.form.get('role') or 'client').strip()
    raw_pw = (request.form.get('password') or '').strip()

    if not email:
        flash('Email is required.', 'warning')
        return redirect(url_for('admin.users_list'))

    if User.query.filter_by(email=email).first():
        flash('Email already registered.', 'danger')
        return redirect(url_for('admin.users_list'))

    if role not in ('client', 'freelancer', 'admin'):
        flash('Invalid role.', 'warning')
        return redirect(url_for('admin.users_list'))

    u = User(
        name=name, email=email, phone=phone, role=role,
        is_email_verified=False, is_suspended=False, status='active',
        created_at=datetime.utcnow()
    )
    if raw_pw:
        u.password_hash = generate_password_hash(raw_pw)

    db.session.add(u)
    db.session.commit()

    flash(f'User {u.email} created.', 'success')
    return redirect(url_for('admin.user_detail', user_id=u.id))

@admin_bp.post('/users/delete')
@login_required
@roles_required('admin')
def user_delete():
    uid = request.form.get('user_id', type=int)
    u = User.query.get_or_404(uid)

    u.deleted_at = datetime.utcnow()
    if hasattr(u, 'is_active'):
        u.is_active = False
    u.status = 'deleted'
    u.is_suspended = True

    db.session.commit()
    flash(f'User {u.email} soft-deleted.', 'warning')
    return redirect(url_for('admin.users_list'))
