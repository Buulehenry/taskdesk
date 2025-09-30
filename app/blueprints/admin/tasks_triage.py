from datetime import datetime
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from ...security import roles_required
from ...extensions import db
from ...models.task import TaskRequest
from ...models.user import User
from ...models.assignment import Assignment
from ...models.quote import Quote
from ...models.invoice import Invoice
from ...services.billing_notifications import email_invoice_created
from .utils import ensure_review_invoice  # should return Invoice or None
from . import admin_bp


@admin_bp.route('/tasks/<int:task_id>', methods=['GET'])
@login_required
@roles_required('admin')
def task_triage(task_id):
    t = TaskRequest.query.get_or_404(task_id)
    freelancers = (
        User.query
        .filter_by(role='freelancer', status='active')
        .order_by(User.name.asc())
        .all()
    )
    return render_template('admin/task_triage.html', task=t, freelancers=freelancers)


@admin_bp.post('/tasks/<int:task_id>/archive')
@login_required
@roles_required('admin')
def task_archive(task_id):
    t = TaskRequest.query.get_or_404(task_id)
    t.status = 'archived'
    db.session.commit()
    flash('Task archived.', 'info')
    return redirect(url_for('admin.inbox'))


@admin_bp.post('/tasks/<int:task_id>/unarchive')
@login_required
@roles_required('admin')
def task_unarchive(task_id):
    t = TaskRequest.query.get_or_404(task_id)
    t.status = 'submitted'
    db.session.commit()
    flash('Task restored.', 'success')
    return redirect(url_for('admin.inbox'))


@admin_bp.post("/tasks/<int:task_id>/status")
@login_required
@roles_required("admin")
def task_set_status(task_id):
    t = TaskRequest.query.get_or_404(task_id)

    # Normalize and validate new status
    new_status = (request.form.get("status") or "").strip().lower()
    if new_status == "canceled":
        new_status = "cancelled"

    allowed = {
        "submitted",
        "quoted",
        "pending_accept",
        "in_progress",
        "review",
        "review_scheduled",
        "awaiting_payment",
        "delivered",
        "closed",
        "cancelled",
        "archived",
    }
    if new_status not in allowed:
        flash("Invalid status.", "warning")
        return redirect(url_for("admin.task_triage", task_id=t.id))

    # Apply transition
    t.status = new_status

    # If entering review/review_scheduled, ensure an unpaid invoice exists
    inv_created = None
    if new_status in {"review", "review_scheduled"}:
        # ensure_review_invoice is idempotent and returns the created Invoice or None
        inv_created = ensure_review_invoice(t)

    db.session.commit()

    # Notify client only if we actually issued a new invoice now
    if inv_created:
        try:
            email_invoice_created(t, inv_created)
        except Exception:
            # Avoid breaking the admin flow if email generation fails
            pass

    flash(f"Status set to {new_status}.", "success")
    return redirect(url_for("admin.task_triage", task_id=t.id))
