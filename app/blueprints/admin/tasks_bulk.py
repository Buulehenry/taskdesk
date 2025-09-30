from datetime import datetime
from flask import request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func
from ...security import roles_required
from ...extensions import db
from ...models.task import TaskRequest
from ...models.assignment import Assignment
from ...models.user import User
from . import admin_bp

@admin_bp.post('/tasks/bulk-assign')
@login_required
@roles_required('admin')
def bulk_assign():
    assignee_id = request.form.get('assignee_id', type=int)
    accept_exp  = (request.form.get('accept_expires_at') or '').strip()
    task_ids    = [int(tid) for tid in request.form.getlist('task_ids') if tid.isdigit()]

    if not task_ids:
        flash('Select at least one task.', 'warning')
        return redirect(url_for('admin.inbox'))

    assignee = User.query.get(assignee_id)
    if not assignee or assignee.role != 'freelancer':
        flash('Invalid freelancer selected.', 'warning')
        return redirect(url_for('admin.inbox'))

    accept_expires_at = None
    if accept_exp:
        try:
            accept_expires_at = datetime.fromisoformat(accept_exp)
        except ValueError:
            flash('Invalid accept-by date. Use YYYY-MM-DDTHH:MM).', 'warning')
            return redirect(url_for('admin.inbox'))

    created, skipped = 0, 0
    for tid in task_ids:
        t = TaskRequest.query.get(tid)
        if not t:
            skipped += 1
            continue

        already = Assignment.query.filter_by(task_id=tid, assignee_id=assignee.id).first()
        if already and already.status in ('pending', 'pending_accept', 'accepted'):
            skipped += 1
            continue

        a = Assignment(
            task_id=tid,
            assignee_id=assignee.id,
            assigned_by=current_user.id,
            accept_expires_at=accept_expires_at,
            status='pending',
        )
        if t.status in ('submitted', 'quoted', 'pending_accept'):
            t.status = 'pending_accept'

        db.session.add(a)
        created += 1

    db.session.commit()
    flash(f'Bulk assign complete: {created} created, {skipped} skipped.', 'success')
    return redirect(url_for('admin.inbox'))

@admin_bp.post('/tasks/bulk-status')
@login_required
@roles_required('admin')
def bulk_status():
    task_ids   = [int(tid) for tid in request.form.getlist('task_ids') if tid.isdigit()]
    new_status = (request.form.get('new_status') or '').strip()

    if not task_ids:
        flash('Select at least one task.', 'warning')
        return redirect(url_for('admin.inbox'))

    allowed = {
        'submitted', 'quoted', 'pending_accept',
        'in_progress', 'review', 'delivered',
        'archived', 'canceled'
    }
    if new_status not in allowed:
        flash('Invalid status selected.', 'danger')
        return redirect(url_for('admin.inbox'))

    tasks = TaskRequest.query.filter(TaskRequest.id.in_(task_ids)).all()
    for t in tasks:
        t.status = new_status

    db.session.commit()
    flash(f'Updated {len(tasks)} task(s) to "{new_status}".', 'success')
    return redirect(url_for('admin.inbox'))
