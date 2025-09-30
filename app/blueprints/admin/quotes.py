from datetime import datetime
from flask import request, redirect, url_for, flash
from flask_login import login_required
from ...security import roles_required
from decimal import Decimal
from ...models.invoice import Invoice
from ...extensions import db
from ...models.task import TaskRequest
from ...models.quote import Quote
from ...services.email_service import send_email
from . import admin_bp



@admin_bp.post('/tasks/<int:task_id>/quotes')
@login_required
@roles_required('admin')
def quote_create(task_id):
    t = TaskRequest.query.get_or_404(task_id)

    raw_price  = (request.form.get('price') or '').strip()
    currency   = (request.form.get('currency') or 'UGX').strip()
    pay_option = (request.form.get('pay_option') or 'pay_on_delivery').strip()
    message    = (request.form.get('message') or '').strip()
    valid_until_raw = (request.form.get('valid_until') or '').strip()

    sanitized = raw_price.replace(',', '').replace(' ', '')
    try:
        price = float(sanitized)
        if price < 0:
            raise ValueError
    except (TypeError, ValueError):
        flash(f'Please enter a valid, non-negative price. Got: {raw_price}', 'warning')
        return redirect(url_for('admin.task_triage', task_id=t.id))

    valid_until = None
    if valid_until_raw:
        try:
            valid_until = datetime.strptime(valid_until_raw, "%Y-%m-%dT%H:%M")
        except Exception:
            valid_until = None

    q = Quote(
        task_id=t.id,
        proposed_price=price,
        currency=currency,
        pay_option=pay_option,
        message=message,
        status='pending',
        created_at=datetime.utcnow(),
        # Include this only if your model has it:
        **({'valid_until': valid_until} if hasattr(Quote, 'valid_until') else {})
    )
    t.status = 'quoted'
    db.session.add(q)
    db.session.commit()

    try:
        if t.client and t.client.email:
            send_email(
                to=t.client.email,
                subject=f"Quote for Task #{t.id} — {t.title}",
                template="quote_created.html",
                task=t,
                quote=q,
            )
    except Exception:
        pass

    flash('Quote created and sent to the client.', 'success')
    return redirect(url_for('admin.task_triage', task_id=t.id))


@admin_bp.post("/quotes/<int:quote_id>/counter/accept")
@roles_required("admin")  # your decorator
def admin_accept_client_counter(quote_id):
    q = Quote.query.get_or_404(quote_id)
    if not (q.status == "countered" and q.client_counter_status == "pending" and q.client_counter_amount):
        flash("This counter offer is not pending.", "warning")
        return redirect(url_for("admin.task_view", task_id=q.task_id))

    # Mark accepted
    q.client_counter_status = "accepted"
    q.status = "accepted"
    q.task.status = "in_progress"

    # If the original quote had a pay_now option, issue invoice with counter amount
    if (q.pay_option or "").lower() == "pay_now":
        inv = Invoice(
            task_id=q.task_id,
            amount=q.client_counter_amount,
            currency=q.client_counter_currency or q.currency,
            status="unpaid",
            issued_at=datetime.utcnow(),
            # ... any other fields
        )
        db.session.add(inv)

    db.session.commit()
    flash("Counter offer accepted. Task started.", "success")
    return redirect(url_for("admin.task_triage", task_id=q.task_id))


@admin_bp.post("/quotes/<int:quote_id>/counter/reject")
@roles_required("admin")
def admin_reject_client_counter(quote_id):
    q = Quote.query.get_or_404(quote_id)
    if not (q.status in ("countered","sent") and q.client_counter_status == "pending"):
        flash("This counter offer is not pending.", "warning")
        return redirect(url_for("admin.task_triage", task_id=q.task_id))

    q.client_counter_status = "rejected"

    # Choice A (recommended): revert quote back to 'sent' to keep original amount alive
    q.status = "sent"

    db.session.commit()
    flash("Counter offer rejected. Original quote remains available.", "info")
    return redirect(url_for("admin.task_triage", task_id=q.task_id))
