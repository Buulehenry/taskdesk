from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from sqlalchemy import func
from app.extensions import db, mail
from ...security import roles_required
from app.models.support import SupportTicket, SupportMessage, SupportAttachment
from datetime import datetime
import os, uuid, mimetypes
from werkzeug.utils import secure_filename
from .utils import email_support_ack, email_support_alert
from . import admin_bp



@admin_bp.route("/tickets")
@login_required
@roles_required('admin')
def tickets_list():
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip().lower()
    page = max(int(request.args.get("page", 1)), 1)
    qry = SupportTicket.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(db.or_(SupportTicket.ticket_id.ilike(like),
                                SupportTicket.email.ilike(like),
                                SupportTicket.name.ilike(like),
                                SupportTicket.category.ilike(like),
                                SupportTicket.message.ilike(like)))
    if status in {"open","pending","closed"}:
        qry = qry.filter(SupportTicket.status == status)
    tickets = qry.order_by(SupportTicket.created_at.desc()).paginate(page=page, per_page=20)
    return render_template("admin/tickets_list.html", tickets=tickets)

@admin_bp.route("/tickets/<int:ticket_id>")
@login_required
@roles_required('admin')
def ticket_detail(ticket_id):
    t = SupportTicket.query.get_or_404(ticket_id)
    page = max(int(request.args.get("page", 1)), 1)
    messages_page = (SupportMessage.query
                     .filter_by(ticket_id=t.id)
                     .order_by(SupportMessage.created_at.asc())
                     .paginate(page=page, per_page=30))
    for m in messages_page.items:
        m.attachments = SupportAttachment.query.filter_by(message_id=m.id).all()
    return render_template("admin/ticket_detail.html", ticket=t, messages_page=messages_page)

@admin_bp.route("/tickets/<int:ticket_id>/reply", methods=["POST"])
@login_required
@roles_required('admin')
def ticket_reply(ticket_id):
    t = SupportTicket.query.get_or_404(ticket_id)
    body = (request.form.get("body") or "").strip()
    if len(body) < 2:
        flash("Message too short.", "warning")
        return redirect(url_for("admin.ticket_detail", ticket_id=ticket_id))
    msg = SupportMessage(ticket_id=t.id, author_user_id=current_user.id, author_role="admin", body=body)
    db.session.add(msg); db.session.flush()

    files = request.files.getlist("attachments")
    upload_base = os.path.join(current_app.instance_path, "support_uploads", datetime.utcnow().strftime("%Y%m%d"))
    os.makedirs(upload_base, exist_ok=True)
    for f in files[:5]:
        if not f or not f.filename: continue
        safe = secure_filename(f.filename)
        dest = os.path.join(upload_base, f"{uuid.uuid4().hex[:10]}-{safe}")
        f.save(dest)
        mime = mimetypes.guess_type(dest)[0] or "application/octet-stream"
        db.session.add(SupportAttachment(ticket_id=t.id, message_id=msg.id, filename=safe, path=dest, size_bytes=os.path.getsize(dest), mime=mime))

    if t.status != "closed":
        t.status = "pending"  # or keep as-is; adjust workflow to your liking

    db.session.commit()

    # notify user of admin reply
    try:
        email_support_ack(t)
    except Exception as e:
        current_app.logger.warning(f"Admin reply email failed: {e}")

    flash("Reply posted.", "success")
    return redirect(url_for("admin.ticket_detail", ticket_id=ticket_id))

@admin_bp.route("/tickets/<int:ticket_id>/status", methods=["POST"])
@login_required
@roles_required('admin')
def ticket_status(ticket_id):
    t = SupportTicket.query.get_or_404(ticket_id)
    new_status = (request.form.get("status") or "").strip().lower()
    if new_status not in {"open","pending","closed"}:
        flash("Invalid status.", "danger")
        return redirect(url_for("admin.ticket_detail", ticket_id=ticket_id))
    t.status = new_status
    db.session.commit()
    flash("Status updated.", "success")
    return redirect(url_for("admin.ticket_detail", ticket_id=ticket_id))
