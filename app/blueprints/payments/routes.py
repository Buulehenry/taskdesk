# app/blueprints/payments/routes.py
from datetime import datetime
from types import SimpleNamespace

from flask import redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user

from ...extensions import db
from ...models.invoice import Invoice
from ...models.task import TaskRequest
from ...services.payment_service import submit_order_request, get_transaction_status
from ...services.billing_notifications import email_payment_received
from . import payments_bp

import json


# -----------------
# Helpers
# -----------------

def _can_pay(inv: Invoice) -> bool:
    """Client who owns the task or an admin can act on the invoice."""
    task: TaskRequest | None = getattr(inv, "task", None) or TaskRequest.query.get(inv.task_id)
    owner_id = getattr(task, "client_id", None)
    return bool(
        getattr(current_user, "is_authenticated", False)
        and (
            getattr(current_user, "role", None) == "admin"
            or (owner_id is not None and owner_id == getattr(current_user, "id", None))
        )
    )


def _build_payment_for_email(inv: Invoice, *, method="online", reference=None):
    """Make a lightweight object with fields the receipt template expects."""
    return SimpleNamespace(
        id=getattr(inv, "id", None),        # use invoice id as a stand-in
        amount=getattr(inv, "amount", 0.0),
        paid_at=getattr(inv, "paid_at", datetime.utcnow()),
        method=method,
        reference=reference or "",
    )


def _safe_flash(msg: str, category: str = "info"):
    """Only flash when there's a request context that can store it (skip IPN)."""
    try:
        flash(msg, category)
    except Exception:
        # IPN or non-standard context – ignore flashing
        pass


# -----------------
# Start payment — redirect to gateway
# -----------------

@payments_bp.route("/pay/<int:invoice_id>")
@login_required
def pay_invoice(invoice_id):
    inv = Invoice.query.get_or_404(invoice_id)
    if not _can_pay(inv):
        _safe_flash("You are not allowed to pay this invoice.", "danger")
        return redirect(url_for("client.dashboard"))
    if inv.status == "paid":
        _safe_flash("This invoice is already paid.", "info")
        return redirect(url_for("client.task_view", task_id=inv.task_id))

    # Ensure a unique merchant reference across attempts
    base_ref = f"INV-{inv.id}"
    uniq_ref = inv.pesapal_merchant_ref or base_ref
    # If we already have a tracking id (previous session) or ref equals base (first time is fine),
    # bump it with a timestamp to avoid "duplicate id" issues at Pesapal.
    if inv.pesapal_tracking_id or uniq_ref == base_ref:
        uniq_ref = f"{base_ref}-{int(datetime.utcnow().timestamp())}"

    inv.pesapal_merchant_ref = uniq_ref
    db.session.commit()

    desc = f"Task #{inv.task_id} invoice #{inv.id}"
    client = getattr(inv.task, "client", None)
    email = getattr(client, "email", "") if client else ""

    try:
        data = submit_order_request(
            merchant_ref=uniq_ref,
            amount=inv.amount,
            currency=(inv.currency or "UGX").upper(),
            description=desc,
            customer_email=email,
        )
    except Exception:
        _safe_flash("Failed to contact payment gateway. Please try again.", "danger")
        return redirect(url_for("client.task_view", task_id=inv.task_id))

    inv.pesapal_tracking_id = data.get("order_tracking_id")
    inv.gateway_status = "PENDING"
    db.session.commit()

    redirect_url = data.get("redirect_url")
    if not redirect_url:
        msg = (
            data.get("status_message")
            or data.get("error")
            or "Failed to create payment session. Check IPN & URLs."
        )
        _safe_flash(msg, "danger")
        return redirect(url_for("client.task_view", task_id=inv.task_id))

    return redirect(redirect_url)


# -----------------
# Sync status helper (used by return + IPN)
# -----------------

def _sync_status_from_pesapal(inv: Invoice, tracking_id: str, *, with_flash: bool = True):
    """Query Pesapal and settle the invoice accordingly (idempotent)."""
    try:
        data = get_transaction_status(tracking_id)  # calls Pesapal API
    except Exception:
        if with_flash:
            _safe_flash("We couldn't verify the payment at the moment. Please refresh in a moment.", "warning")
        return

    # Persist gateway payload for auditing
    try:
        # If your column is JSON, assigning dict is fine; if it's Text, serialize:
        inv.gateway_meta = data if hasattr(type(inv), "gateway_meta").type.python_type is dict else json.dumps(data)
    except Exception:
        # Fallback to text
        try:
            inv.gateway_meta = json.dumps(data)
        except Exception:
            pass

    inv.pesapal_tracking_id = tracking_id or inv.pesapal_tracking_id
    status_desc = (data.get("payment_status_description") or "").upper()  # COMPLETED/PENDING/FAILED/REVERSED
    inv.gateway_status = status_desc

    if status_desc == "COMPLETED":
        if inv.status != "paid":
            inv.status = "paid"
            inv.paid_at = datetime.utcnow()
            db.session.commit()
            # Email receipt once (idempotent guard above)
            try:
                task = inv.task or TaskRequest.query.get(inv.task_id)
                if task and getattr(task, "client", None) and task.client.email:
                    payment = {
                        "provider": "Pesapal",
                        "tracking_id": tracking_id,
                        "amount": inv.amount,
                        "paid_at": inv.paid_at,
                    }
                    email_payment_received(task, inv, payment)
            except Exception:
                pass
        if with_flash:
            _safe_flash("Payment successful.", "success")

    elif status_desc in {"FAILED", "REVERSED"}:
        if inv.status != "paid":
            inv.status = "unpaid"
            db.session.commit()
        if with_flash:
            _safe_flash("Payment failed or reversed.", "danger")

    else:
        # PENDING or unknown status — keep metadata, leave as-is
        db.session.commit()
        if with_flash:
            _safe_flash("Payment is still pending. We’ll update this page when it clears.", "info")


# -----------------
# Payment return/callback (public)
# -----------------

@payments_bp.route("/return")
def pay_return():
    tracking = (
        request.args.get("OrderTrackingId")
        or request.args.get("orderTrackingId")
        or request.args.get("tracking")
    )
    merchant_ref = (
        request.args.get("OrderMerchantReference")
        or request.args.get("orderMerchantReference")
        or request.args.get("merchant_ref")
    )

    if tracking and merchant_ref:
        inv = Invoice.query.filter_by(pesapal_merchant_ref=merchant_ref).first()
        if not inv:
            _safe_flash("We couldn't match this payment to an invoice.", "warning")
            return redirect(url_for("client.dashboard"))
        _sync_status_from_pesapal(inv, tracking, with_flash=True)
        return redirect(url_for("client.task_view", task_id=inv.task_id))

    # --- Legacy/mock fallback ---
    invoice_id = request.args.get("invoice_id", type=int)
    status = (request.args.get("status") or "cancel").lower()
    ref = request.args.get("ref")

    if invoice_id:
        inv = Invoice.query.get_or_404(invoice_id)
        if status == "success":
            already_paid = (inv.status == "paid")
            inv.status = "paid"
            inv.paid_at = datetime.utcnow()
            db.session.commit()
            if not already_paid:
                try:
                    task = inv.task or TaskRequest.query.get(inv.task_id)
                    email_payment_received(task, inv, {"provider": "Mock", "reference": ref})
                except Exception:
                    pass
            _safe_flash("Payment successful.", "success")
        else:
            if inv.status != "paid":
                inv.status = "unpaid"
                db.session.commit()
            _safe_flash("Payment canceled.", "info")
        return redirect(url_for("client.task_view", task_id=inv.task_id))

    # No params at all → be friendly, not a 400
    _safe_flash("Payment return did not include the expected parameters.", "warning")
    return redirect(url_for("client.dashboard"))


# -----------------
# Mock gateway — mark invoice paid (for local/testing)
# -----------------

@payments_bp.route("/mock/<int:invoice_id>")
@login_required
def mock_pay(invoice_id):
    inv = Invoice.query.get_or_404(invoice_id)
    if not _can_pay(inv):
        _safe_flash("You are not allowed to pay this invoice.", "danger")
        return redirect(url_for("client.dashboard"))

    # Idempotency
    already_paid = (inv.status == "paid")
    inv.status = "paid"
    inv.paid_at = datetime.utcnow()
    db.session.commit()

    if not already_paid:
        try:
            task = inv.task or TaskRequest.query.get(inv.task_id)
            payment = _build_payment_for_email(inv, method="mock", reference="MOCK-OK")
            email_payment_received(task, inv, payment)
        except Exception:
            pass

    _safe_flash("Payment successful (mock).", "success")
    return redirect(url_for("client.task_view", task_id=inv.task_id))
