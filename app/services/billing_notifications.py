# app/services/billing_notifications.py
from pathlib import Path
from flask import url_for, current_app
from .pdf_service import render_pdf
from ..services.email_service import send_email

def email_invoice_created(task, invoice) -> bool:
    if not getattr(task, "client", None) or not task.client.email:
        return False
    pdf_bytes = None
    try:
        pdf_bytes = render_pdf("pdf/invoice.html", task=task, invoice=invoice)
    except Exception:
        pdf_bytes = None

    kwargs = dict(
        to=task.client.email,
        subject=f"Invoice issued — Task #{task.id}",
        template="invoice_created_client.html",
        task=task,
        invoice=invoice,
        pay_url=url_for("payments.pay_invoice", invoice_id=invoice.id, _external=True),
        task_link=url_for("client.task_view", task_id=task.id, _external=True),
    )
    if pdf_bytes:
        # (filename, bytes, mimetype)
        kwargs["attachments"] = [(f"invoice_{invoice.id}.pdf", pdf_bytes, "application/pdf")]
    return bool(send_email(**kwargs))

def email_payment_received(task, invoice, payment: dict) -> bool:
    if not getattr(task, "client", None) or not task.client.email:
        return False

    pdf_bytes = None
    try:
        pdf_bytes = render_pdf("pdf/receipt.html", task=task, invoice=invoice, payment=payment)
    except Exception:
        pdf_bytes = None

    inline_images = []
    logo_cid = "td-logo"
    try:
        logo_path = Path(current_app.static_folder) / "img" / "logo.png"
        if logo_path.exists():
            inline_images.append({
                "cid": logo_cid,
                "filename": "logo.png",
                "mimetype": "image/png",
                "data": logo_path.read_bytes(),
            })
    except Exception:
        pass

    kwargs = dict(
        to=task.client.email,
        subject=f"Payment received — Task #{task.id}",
        template="payment_received_client.html",
        task=task,
        invoice=invoice,
        payment=payment,
        task_link=url_for("client.task_view", task_id=task.id, _external=True),
        inline_images=inline_images or None,
        logo_cid=logo_cid,
    )
    if pdf_bytes:
        kwargs["attachments"] = [(f"receipt_{invoice.id}.pdf", pdf_bytes, "application/pdf")]
    return bool(send_email(**kwargs))
