from datetime import datetime
from flask import request, redirect, url_for, flash
from flask_login import login_required, current_user
from ...security import roles_required
from ...extensions import db
from ...models.task import TaskRequest
from ...models.user import User
from ...models.assignment import Assignment
from ...services.email_service import send_email
from . import admin_bp

@admin_bp.post('/tasks/<int:task_id>/assignments')
@login_required
@roles_required('admin')
def assignment_create(task_id):
    t = TaskRequest.query.get_or_404(task_id)

    assignee_raw = (request.form.get('assignee_id') or '').strip()
    try:
        assignee_id = int(assignee_raw)
    except (TypeError, ValueError):
        flash('Invalid assignee.', 'warning')
        return redirect(url_for('admin.task_triage', task_id=t.id))

    assignee = User.query.get(assignee_id)
    if not assignee or assignee.role != 'freelancer':
        flash('Selected user is not a valid freelancer.', 'warning')
        return redirect(url_for('admin.task_triage', task_id=t.id))

    accept_expires_at = None
    raw_exp = (request.form.get('accept_expires_at') or '').strip()
    if raw_exp:
        try:
            accept_expires_at = datetime.fromisoformat(raw_exp)
        except ValueError:
            flash('Invalid accept-by date. Use YYYY-MM-DDTHH:MM format.', 'warning')
            return redirect(url_for('admin.task_triage', task_id=t.id))

    a = Assignment(
        task_id=t.id,
        assignee_id=assignee.id,
        assigned_by=current_user.id,
        accept_expires_at=accept_expires_at,
        status='pending',
    )
    if t.status in ('submitted', 'quoted', 'pending_accept'):
        t.status = 'pending_accept'

    db.session.add(a)
    db.session.commit()

    try:
        send_email(
            to=assignee.email,
            subject=f"TaskDesk Assignment — Task #{t.id}",
            template='assignment_invite.html',
            assignment=a,
            task=t,
        )
        flash('Assignment created and email sent.', 'success')
    except Exception:
        flash('Assignment created. Email failed to send; notify manually.', 'warning')

    return redirect(url_for('admin.task_triage', task_id=t.id))
