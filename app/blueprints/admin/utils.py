import os, mimetypes
from io import BytesIO
from hashlib import md5
from flask import abort, current_app
from datetime import datetime
from ...extensions import db, mail
from ...models.fileasset import FileAsset
from ...models.invoice import Invoice
from ...models.quote import Quote
from flask_mail import Message
# ----- Private storage roots (outside static/) -----

def _PRIVATE_ROOT():
    # e.g. instance/uploads
    return os.path.join(current_app.instance_path, "uploads")

def _THUMBS_ROOT():
    # e.g. instance/cache/thumbs
    return os.path.join(current_app.instance_path, "cache", "thumbs")

def _safe_abs_path(relpath: str) -> str:
    base = os.path.normpath(_PRIVATE_ROOT())
    abs_path = os.path.normpath(os.path.join(base, relpath or ""))
    if not abs_path.startswith(base):
        abort(403)
    return abs_path

def _load_asset_stream(asset: FileAsset):
    abs_path = _safe_abs_path(asset.path)
    if not os.path.exists(abs_path):
        abort(404)
    mime = asset.mime or (mimetypes.guess_type(asset.filename or abs_path)[0] or "application/octet-stream")
    with open(abs_path, "rb") as f:
        data = f.read()
    return BytesIO(data), mime, (asset.filename or os.path.basename(abs_path))

def _etag(b: bytes) -> str:
    return md5(b).hexdigest()

def _record_admin_audit(actor_id: int, action: str, targets: list[int], meta: dict | None = None):
    # Example stub; adapt to your audit model/table if you have one.
    # from ...models.audit import AdminAudit
    # db.session.add(AdminAudit(actor_id=actor_id, action=action, targets=targets, meta=meta))
    # db.session.commit()
    pass

def ensure_review_invoice(task):
    """If the task has an accepted pay_on_delivery quote and no unpaid invoice,
    create one. Safe to call multiple times (idempotent)."""
    # already has an unpaid invoice?
    if any(getattr(inv, "status", None) == "unpaid" for inv in (task.invoices or [])):
        return None

    # find accepted quote
    accepted = None
    if getattr(task, "quotes", None):
        # latest accepted
        for q in sorted(task.quotes, key=lambda x: x.id, reverse=True):
            if getattr(q, "status", "") == "accepted":
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

def email_support_ack(ticket):
    """
    Send an acknowledgement/receipt to the end user for ticket creation
    or to notify them that support has replied.
    """
    if "mail" not in current_app.extensions:  # graceful no-mail fallback
        current_app.logger.info(f"[email stub] ACK -> {ticket.email} for {ticket.ticket_id}")
        return

    sender_name = current_app.config.get("MAIL_DEFAULT_SENDER_NAME", "TaskDesk Support")
    sender_addr = current_app.config.get("MAIL_DEFAULT_SENDER")

    msg = Message(
        subject=f"[TaskDesk] Ticket {ticket.ticket_id}",
        sender=(sender_name, sender_addr),
        recipients=[ticket.email],
        body=(
            f"Hi {ticket.name},\n\n"
            f"Your support ticket {ticket.ticket_id} ({ticket.category}) is in our queue.\n\n"
            f"Message:\n{ticket.message}\n\n"
            f"You can reply or view status here:\n"
            f"{current_app.config.get('EXTERNAL_BASE_URL','http://localhost:5000')}/support/t/{ticket.ticket_id}\n\n"
            f"— TaskDesk Support"
        ),
    )
    mail.send(msg)

def email_support_alert(ticket):
    """
    Notify internal support team a new ticket or user reply arrived.
    """
    if "mail" not in current_app.extensions:  # graceful no-mail fallback
        current_app.logger.info(f"[email stub] ALERT -> team for {ticket.ticket_id}")
        return

    to_list = current_app.config.get("SUPPORT_TEAM_EMAILS", ["support@taskdesk.example"])
    sender_name = current_app.config.get("MAIL_DEFAULT_SENDER_NAME", "TaskDesk Support")
    sender_addr = current_app.config.get("MAIL_DEFAULT_SENDER")

    msg = Message(
        subject=f"[TaskDesk] NEW/UPDATE {ticket.ticket_id} — {ticket.category}",
        sender=(sender_name, sender_addr),
        recipients=to_list,
        reply_to=ticket.email,
        body=(
            f"Ticket: {ticket.ticket_id}\n"
            f"From: {ticket.name} <{ticket.email}>\n"
            f"Category: {ticket.category}\n"
            f"Status: {ticket.status}\n\n"
            f"{ticket.message}\n"
        ),
    )
    mail.send(msg)