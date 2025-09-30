# app/blueprints/client/routes.py
from datetime import datetime
from decimal import Decimal
from typing import Optional

from flask import render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename
from ...services.billing_notifications import email_invoice_created

from . import client_bp
from ...extensions import db
from ...models.task import TaskRequest
from ...models.quote import Quote
from ...models.invoice import Invoice
from ...models.fileasset import FileAsset
from ...services.storage_service import save_upload, allowed_ext


# -----------------
# Helpers
# -----------------

def _parse_dt(val: str) -> Optional[datetime]:
    if not val:
        return None
    try:
        # Accept both YYYY-MM-DD and full ISO strings
        return datetime.fromisoformat(val)
    except Exception:
        return None


def _currency() -> str:
    prof = getattr(current_user, "client_profile", None)
    return (prof.default_currency if prof and prof.default_currency else "USD")


def _ensure_owner(task: TaskRequest):
    if task.client_id != current_user.id:
        abort(403)

def _owns_task(task: TaskRequest) -> bool:
    return current_user.is_authenticated and getattr(task, "client_id", None) == current_user.id

# -----------------
# Dashboard
# -----------------

@client_bp.route('/dashboard')
@login_required
def dashboard():
    # Prefetch quotes and invoices for faster cards in the dashboard
    my_tasks = (
        TaskRequest.query
        .options(joinedload(TaskRequest.quotes), joinedload(TaskRequest.invoices))
        .filter_by(client_id=current_user.id)
        .order_by(TaskRequest.id.desc())
        .all()
    )

    # Simple KPIs for the header (optional in your template)
    total = len(my_tasks)
    pending = sum(1 for t in my_tasks if t.status in ('new', 'awaiting_quote'))
    active = sum(1 for t in my_tasks if t.status in ('in_progress', 'review'))
    closed = sum(1 for t in my_tasks if t.status in ('delivered', 'closed'))

    return render_template('client/dashboard.html', tasks=my_tasks,
                           kpis=dict(total=total, pending=pending, active=active, closed=closed))


# -----------------
# Create Task
# -----------------

@client_bp.route('/tasks/new', methods=['GET', 'POST'])
@login_required
def task_new():
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()
        description = (request.form.get('description') or '').strip()
        category = (request.form.get('category') or '').strip()
        deadline = _parse_dt(request.form.get('deadline'))
        budget_raw = (request.form.get('budget') or '').strip()

        if not title:
            flash('Title is required.', 'warning')
            return render_template('client/task_new.html')

        t = TaskRequest(
            client_id=current_user.id,
            title=title,
            description=description,
            category=category,
            deadline_at=deadline,
        )

        if budget_raw:
            try:
                t.client_budget = float(budget_raw)
            except ValueError:
                flash('Budget must be a number.', 'warning')

        db.session.add(t)
        db.session.flush()  # ensures t.id is available

        # Handle attachments (multi)
        files = request.files.getlist('attachments')
        for f in files:
            if not f or not f.filename:
                continue
            safe_name = secure_filename(f.filename)
            if not safe_name:
                continue
            if not allowed_ext(safe_name):
                flash(f'Skipped unsupported file: {safe_name}', 'info')
                continue

            stored_path = save_upload(f, subdir=f"client/{current_user.id}/tasks/{t.id}")
            asset = FileAsset(
                owner_id=current_user.id,
                task_id=t.id,
                path=stored_path,
                filename=safe_name,
                mime=f.mimetype,
                size_bytes=getattr(f, 'content_length', None),
            )
            db.session.add(asset)

        # New tasks start in awaiting_quote so admin can triage
        if not t.status:
            t.status = 'awaiting_quote'

        db.session.commit()
        flash('Task submitted. You will receive a quote shortly.', 'success')
        return redirect(url_for('client.dashboard'))

    return render_template('client/task_new.html')


# -----------------
# View Task + Upload More Files
# -----------------

@client_bp.route('/tasks/<int:task_id>')
@login_required
def task_view(task_id):
    t = (TaskRequest.query
         .options(joinedload(TaskRequest.quotes), joinedload(TaskRequest.invoices))
         .get_or_404(task_id))
    _ensure_owner(t)

    quotes = sorted((t.quotes or []), key=lambda q: q.id, reverse=True)
    invoices = sorted((t.invoices or []), key=lambda i: i.id, reverse=True)
    assets = (FileAsset.query
              .filter_by(task_id=t.id)
              .order_by(FileAsset.id.desc())
              .all())

    return render_template('client/task_view.html', task=t, quotes=quotes, invoices=invoices, assets=assets)


@client_bp.post('/tasks/<int:task_id>/attachments')
@login_required
def task_add_attachments(task_id):
    t = TaskRequest.query.get_or_404(task_id)
    _ensure_owner(t)

    files = request.files.getlist('attachments')
    added = 0
    for f in files:
        if not f or not f.filename:
            continue
        safe_name = secure_filename(f.filename)
        if not safe_name:
            continue
        if not allowed_ext(safe_name):
            flash(f'Skipped unsupported file: {safe_name}', 'info')
            continue
        stored_path = save_upload(f, subdir=f"client/{current_user.id}/tasks/{t.id}")
        asset = FileAsset(
            owner_id=current_user.id,
            task_id=t.id,
            path=stored_path,
            filename=safe_name,
            mime=f.mimetype,
            size_bytes=getattr(f, 'content_length', None),
        )
        db.session.add(asset)
        added += 1

    db.session.commit()
    if added:
        flash(f'Uploaded {added} file(s).', 'success')
    else:
        flash('No files uploaded.', 'info')
    return redirect(url_for('client.task_view', task_id=t.id))


# -----------------
# Quotes → Accept / Decline
# -----------------

@client_bp.post("/client/quotes/<int:quote_id>/accept")
@login_required
def quote_accept(quote_id):
    q = Quote.query.get_or_404(quote_id)
    t = TaskRequest.query.get_or_404(q.task_id)

    # Basic ownership check (TODO: adapt if you allow org members/admins here)
    if not _owns_task(t):
        flash("You’re not allowed to accept this quote.", "danger")
        return redirect(url_for("client.task_view", task_id=t.id))

    # Only allow accepting quotes that are actionable
    if (q.status or "").lower() not in {"sent", "pending", "countered"}:
        flash("This quote cannot be accepted.", "warning")
        return redirect(url_for("client.task_view", task_id=t.id))

    # Accept quote
    q.status = "accepted"
    t.status = "in_progress"  # or "awaiting_payment" if you prefer to block until paid for pay_now

    inv = None  # IMPORTANT: initialize so we can safely check later

    # If pay_now, issue invoice immediately
    if (q.pay_option or "").lower() == "pay_now":
        inv = Invoice(
            task_id=t.id,
            amount=q.client_counter_amount or q.proposed_price,  # if they negotiated, use agreed amount
            currency=q.client_counter_currency or q.currency,
            status="unpaid",
            issued_at=datetime.utcnow(),
        )
        db.session.add(inv)

    db.session.commit()

    # Email the invoice only if one was created
    if inv is not None:
        try:
            email_invoice_created(t, inv)
        except Exception:
            # don't block the flow on email/pdf failures
            pass

    flash("Quote accepted.", "success")
    return redirect(url_for("client.task_view", task_id=t.id))


@client_bp.post("/quotes/<int:quote_id>/decline")
@login_required
def quote_decline(quote_id):
    q = Quote.query.get_or_404(quote_id)

    # ---- Ownership / permission check ----
    task = getattr(q, "task", None)
    client_id = getattr(task, "client_id", None)

    # allow if this user owns the task ...
    is_owner = (client_id is not None and current_user.id == client_id)

    # ... or if user is privileged staff/admin (optional helper)
    role = getattr(current_user, "role", "") or ""
    is_staff = role in {"admin", "staff"} or getattr(current_user, "is_staff", False)

    if not (is_owner or is_staff):
        # Hide details; just deny
        abort(403)

    # Quote must be actionable
    if q.status not in {"sent", "pending"}:
        flash("This quote can’t be declined or countered in its current state.", "warning")
        return redirect(url_for("client.task_view", task_id=q.task_id))

    # Prevent stacking counters
    if (q.client_counter_status or "").lower() == "pending":
        flash("A counter offer is already pending review.", "info")
        return redirect(url_for("client.task_view", task_id=q.task_id))

    # ---- Handle decline with optional counter offer ----
    amount_raw = (request.form.get("client_counter_amount") or "").strip()
    reason = (request.form.get("client_counter_reason") or "").strip()

    if amount_raw:
        try:
            amount = Decimal(amount_raw.replace(",", "").replace(" ", ""))
            if amount < 0:
                raise ValueError
        except Exception:
            flash("Please enter a valid amount.", "warning")
            return redirect(url_for("client.task_view", task_id=q.task_id))

        q.client_counter_amount = amount
        q.client_counter_currency = q.currency
        q.client_counter_reason = reason or None
        q.client_counter_status = "pending"
        q.client_counter_at = datetime.utcnow()
        q.status = "countered"
        db.session.commit()

        # (Optional) notify admins — if you added the email step earlier
        # try:
        #     from flask import current_app
        #     from ...services.email_service import send_email
        #     admin_emails = current_app.config.get("ADMIN_EMAILS", [])
        #     if isinstance(admin_emails, str): admin_emails = [admin_emails]
        #     if admin_emails:
        #         send_email(
        #             to=admin_emails,
        #             subject=f"[Counter Offer] Task #{q.task.id} — {q.task.title}",
        #             template="counter_submitted_admin.html",
        #             task=q.task,
        #             quote=q,
        #             admin_triage_link=url_for("admin.task_triage", task_id=q.task_id, _external=True),
        #         )
        # except Exception:
        #     pass

        flash("Counter offer submitted. We’ll get back to you shortly.", "success")
        return redirect(url_for("client.task_view", task_id=q.task_id))

    # True decline (no counter)
    q.status = "declined"
    db.session.commit()
    flash("Quote declined.", "info")
    return redirect(url_for("client.task_view", task_id=q.task_id))



# -----------------
# Optional: Cancel task (only if not already in progress)
# -----------------

@client_bp.post('/tasks/<int:task_id>/cancel')
@login_required
def task_cancel(task_id):
    t = TaskRequest.query.get_or_404(task_id)
    _ensure_owner(t)

    if t.status in ('in_progress', 'review', 'delivered', 'closed'):
        flash('Task cannot be canceled at this stage.', 'warning')
        return redirect(url_for('client.task_view', task_id=t.id))

    t.status = 'canceled'
    db.session.commit()
    flash('Task canceled.', 'info')
    return redirect(url_for('client.dashboard'))
