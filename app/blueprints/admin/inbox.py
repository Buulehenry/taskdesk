from flask import render_template, request, redirect, url_for
from flask_login import login_required
from sqlalchemy.orm import selectinload
from sqlalchemy import or_, asc, desc, func
from ...security import roles_required
from ...extensions import db
from ...models.task import TaskRequest
from ...models.user import User
from ...models.assignment import Assignment
from . import admin_bp
from datetime import datetime
from ...models.invoice import Invoice
from ...models.quote import Quote

@admin_bp.route('/inbox')
@login_required
@roles_required('admin')
def inbox():
    q        = (request.args.get('q') or '').strip()
    status   = (request.args.get('status') or '').strip()
    sort     = request.args.get('sort', '-created').strip()
    page     = max(int(request.args.get('page', 1) or 1), 1)
    per_page = min(int(request.args.get('per_page', 20) or 20), 100)

    base = (
        TaskRequest.query.options(
            selectinload(TaskRequest.client),
            selectinload(TaskRequest.quotes),
            selectinload(TaskRequest.assignments).selectinload(Assignment.assignee),
        )
    )

    if q:
        like = f"%{q}%"
        base = (
            base.outerjoin(User, TaskRequest.client_id == User.id)
                .filter(
                    or_(
                        TaskRequest.title.ilike(like),
                        TaskRequest.category.ilike(like),
                        func.cast(TaskRequest.id, db.String).ilike(like),
                        User.name.ilike(like),
                        User.email.ilike(like),
                    )
                )
        )

    if status:
        base = base.filter(TaskRequest.status == status)

    if sort == 'created':
        base = base.order_by(asc(TaskRequest.created_at))
    elif sort == '-created':
        base = base.order_by(desc(TaskRequest.created_at))
    elif sort == 'deadline':
        base = base.order_by(asc(TaskRequest.deadline_at))
    elif sort == '-deadline':
        base = base.order_by(desc(TaskRequest.deadline_at))
    else:
        base = base.order_by(desc(TaskRequest.created_at))

    total = base.count()
    pages = max((total + per_page - 1) // per_page, 1)
    page = min(page, pages)
    tasks = base.offset((page - 1) * per_page).limit(per_page).all()

    statuses = [
        'Submitted', 'Quoted', 'Pending Accept',
        'In Progress', 'Review', 'Delivered',
        'Archived', 'Canceled'
    ]
    counts = {s: 0 for s in statuses}
    for s, c in db.session.query(TaskRequest.status, func.count()).group_by(TaskRequest.status).all():
        if s in counts:
            counts[s] = c

    freelancers = (
        User.query
        .filter_by(role='freelancer', status='active')
        .order_by(User.name.asc())
        .all()
    )

    return render_template(
        'admin/inbox.html',
        tasks=tasks,
        freelancers=freelancers,
        counts=counts,
        page=page,
        pages=pages,
    )

@admin_bp.route('/dashboard')
@login_required
@roles_required('admin')
def dashboard():
    return redirect(url_for('admin.inbox'))


def _ensure_review_invoice(task):
    """If task has an accepted pay_on_delivery quote and no unpaid invoice, create one."""
    # already have an unpaid invoice?
    if any(getattr(inv, "status", None) == "unpaid" for inv in (task.invoices or [])):
        return None

    # find most-recent accepted quote
    accepted = None
    if getattr(task, "quotes", None):
        for q in sorted(task.quotes, key=lambda x: x.id, reverse=True):
            if (q.status or "").lower() == "accepted":
                accepted = q
                break
    if not accepted:
        return None

    if (accepted.pay_option or "").lower() != "pay_on_delivery":
        return None

    inv = Invoice(
        task_id=task.id,
        amount=accepted.proposed_price,
        currency=accepted.currency,
        status="unpaid",
        issued_at=datetime.utcnow(),
    )
    db.session.add(inv)
    db.session.commit()
    return inv


# --- route to update the status from inbox ---
@admin_bp.post("/tasks/<int:task_id>/status")
@login_required
@roles_required("admin")
def inbox_set_status(task_id):
    t = TaskRequest.query.options(
        selectinload(TaskRequest.quotes),
        selectinload(TaskRequest.invoices),
    ).get_or_404(task_id)

    # Expect values like: submitted, quoted, in_progress, review, review_scheduled, delivered, closed, cancelled
    new_status = (request.form.get("status") or "").strip().lower()

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
        "canceled",   # tolerate US spelling from UI
    }
    if new_status not in allowed:
        # fall back to current to avoid bad writes
        return redirect(request.referrer or url_for("admin.inbox"))

    # Normalize spelling
    if new_status == "canceled":
        new_status = "cancelled"

    t.status = new_status

    # If entering review, ensure invoice exists for pay_on_delivery
    if new_status in {"review", "review_scheduled"}:
        _ensure_review_invoice(t)

    db.session.commit()

    # go back to inbox (preserve filters if any)
    return redirect(request.referrer or url_for("admin.inbox"))
