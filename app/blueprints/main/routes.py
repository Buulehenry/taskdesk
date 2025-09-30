# imports at top:
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify, session, make_response
from datetime import datetime, timedelta
import json
from flask_login import current_user, login_required
from sqlalchemy import func
from datetime import datetime, timedelta
import os, uuid, mimetypes
from werkzeug.utils import secure_filename
from urllib.parse import urlparse
from app.extensions import db, mail
from app.models.support import SupportTicket, SupportAttachment, SupportMessage

from . import main_bp

@main_bp.route("/privacy")
def privacy():
    return render_template("static/privacy.html")

@main_bp.route("/terms")
def terms():
    return render_template("static/terms.html")

@main_bp.route("/support")
def support():
    # If logged in, fetch a few recent tickets to show in-page
    tickets = None
    if current_user.is_authenticated:
        tickets = (SupportTicket.query
                   .filter((SupportTicket.user_id == current_user.id) |
                           (SupportTicket.email == func.lower(current_user.email)))
                   .order_by(SupportTicket.created_at.desc())
                   .limit(10)
                   .all())
    return render_template("static/support.html", tickets=tickets)

# ---- Spam throttle config (simple DB-based) ----
THROTTLE_WINDOW_MIN = 10
THROTTLE_MAX = 3  # max tickets per email/IP in window
ALLOWED_EXTS = {"png","jpg","jpeg","gif","pdf","mp4","txt","zip"}
MAX_FILES = 5
MAX_EACH_FILE_MB = 10

def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTS

def _client_ip():
    h = request.headers.get("X-Forwarded-For", "")  # respect proxy
    return (h.split(",")[0].strip() if h else request.remote_addr) or "0.0.0.0"

@main_bp.route("/support/new", methods=["POST"])
def support_new():
    # Honeypot
    if request.form.get("website"):
        flash("Submission received.", "info")
        return redirect(url_for("main.support"))

    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    category = (request.form.get("category") or "").strip()
    message = (request.form.get("message") or "").strip()
    ip = _client_ip()

    # ---- Throttle by email/IP in last N minutes ----
    window_start = datetime.utcnow() - timedelta(minutes=THROTTLE_WINDOW_MIN)
    recent_count = (SupportTicket.query
                    .filter(SupportTicket.created_at >= window_start)
                    .filter((SupportTicket.email == email) | (SupportTicket.ip_address == ip))
                    .count())
    if recent_count >= THROTTLE_MAX:
        flash("You’ve reached the submission limit. Please try again later.", "warning")
        return redirect(url_for("main.support") + "#contact")

    # Validation
    errors = []
    if not name: errors.append("Name is required.")
    if not email or "@" not in email: errors.append("Valid email is required.")
    if not category: errors.append("Category is required.")
    if not message or len(message) < 10: errors.append("Message must be at least 10 characters.")
    files = request.files.getlist("attachments")
    if len(files) > MAX_FILES: errors.append(f"Attach at most {MAX_FILES} files.")
    if errors:
        for e in errors: flash(e, "danger")
        return redirect(url_for("main.support") + "#contact")

    # Create ticket
    ticket_code = uuid.uuid4().hex[:8].upper()
    ticket = SupportTicket(
        ticket_id=ticket_code,
        user_id=(current_user.id if current_user.is_authenticated else None),
        ip_address=ip,
        name=name, email=email, category=category, message=message, status="open"
    )
    db.session.add(ticket)
    db.session.flush()

    # Save files
    upload_base = os.path.join(current_app.instance_path, "support_uploads", datetime.utcnow().strftime("%Y%m%d"))
    os.makedirs(upload_base, exist_ok=True)
    for f in files:
        if not f or not f.filename:
            continue
        if not _allowed_file(f.filename):
            flash(f"Unsupported file type: {f.filename}", "info")
            continue
        f.seek(0, os.SEEK_END); size = f.tell(); f.seek(0)
        if size > MAX_EACH_FILE_MB*1024*1024:
            flash(f"{f.filename} exceeds {MAX_EACH_FILE_MB}MB", "warning")
            continue
        safe = secure_filename(f.filename)
        fname = f"{uuid.uuid4().hex[:10]}-{safe}"
        dest = os.path.join(upload_base, fname)
        f.save(dest)
        mime = mimetypes.guess_type(dest)[0] or "application/octet-stream"
        db.session.add(SupportAttachment(ticket_id=ticket.id, filename=safe, path=dest, size_bytes=size, mime=mime))

    db.session.commit()

    # Emails (best-effort)
    try:
        _email_support_ack(ticket)
        _email_support_alert(ticket)
    except Exception as e:
        current_app.logger.warning(f"Support email send failed: {e}")

    flash(f"Thanks {name}! Your ticket #{ticket.ticket_id} was submitted.", "success")
    return redirect(url_for("main.support") + "#contact")

# Email helpers
from flask_mail import Message
def _email_support_ack(ticket):
    sender_name = current_app.config.get("MAIL_DEFAULT_SENDER_NAME", "TaskDesk Support")
    sender_addr = current_app.config.get("MAIL_DEFAULT_SENDER")
    mail.send(Message(
        subject=f"[TaskDesk] Ticket {ticket.ticket_id} received",
        sender=(sender_name, sender_addr),
        recipients=[ticket.email],
        body=(f"Hi {ticket.name},\n\nThanks for contacting TaskDesk support. "
              f"Your ticket {ticket.ticket_id} ({ticket.category}) has been received.\n\n"
              f"Your message:\n{ticket.message}\n\n— TaskDesk Support")
    ))

def _email_support_alert(ticket):
    to_list = current_app.config.get("SUPPORT_TEAM_EMAILS", ["hbhens@outlook.com"])
    sender_name = current_app.config.get("MAIL_DEFAULT_SENDER_NAME", "TaskDesk Support")
    sender_addr = current_app.config.get("MAIL_DEFAULT_SENDER")
    mail.send(Message(
        subject=f"[TaskDesk] NEW Ticket {ticket.ticket_id} — {ticket.category}",
        sender=(sender_name, sender_addr),
        recipients=to_list,
        reply_to=ticket.email,
        body=(f"From: {ticket.name} <{ticket.email}>\nIP: {ticket.ip_address}\n"
              f"Ticket: {ticket.ticket_id}\nCategory: {ticket.category}\n\n{ticket.message}\n")
    ))

# ---- Tiny JSON health route (DB ping + version) ----
@main_bp.route("/status")
def status():
    ok_db = True
    try:
        db.session.execute(db.text("SELECT 1"))
    except Exception as e:
        current_app.logger.error(f"DB health failed: {e}")
        ok_db = False

    payload = {
        "service": "taskdesk",
        "version": current_app.config.get("APP_VERSION"),
        "time_utc": datetime.utcnow().isoformat() + "Z",
        "checks": {"database": "ok" if ok_db else "fail"},
    }
    code = 200 if ok_db else 503

    # ?pretty=1 -> pretty JSON
    if request.args.get("pretty"):
        import json
        return current_app.response_class(
            json.dumps(payload, indent=2) + "\n",
            mimetype="application/json"
        ), code

    # If the browser prefers HTML (or ?format=html), show a styled page
    wants_html = "text/html" in request.accept_mimetypes or request.args.get("format") == "html"
    if wants_html and request.args.get("format") != "json":
        return render_template("status.html", h=payload, healthy=ok_db), code

    # Default: compact JSON for monitors
    return jsonify(payload), code


@main_bp.route("/support/my")
@login_required
def support_my():
    q = (request.args.get("q") or "").strip().lower()
    status = (request.args.get("status") or "").strip().lower()
    page = max(int(request.args.get("page", 1)), 1)

    qry = SupportTicket.query.filter(
        (SupportTicket.user_id == current_user.id) |
        (SupportTicket.email == func.lower(current_user.email))
    )
    if q:
        like = f"%{q}%"
        qry = qry.filter(
            db.or_(
                SupportTicket.ticket_id.ilike(like),
                SupportTicket.category.ilike(like),
                SupportTicket.status.ilike(like),
                SupportTicket.message.ilike(like),
            )
        )
    if status in {"open","pending","closed"}:
        qry = qry.filter(SupportTicket.status == status)

    tickets = qry.order_by(SupportTicket.created_at.desc()).paginate(page=page, per_page=10)
    return render_template("client/support_my.html", tickets=tickets)

@main_bp.route("/support/t/<ticket_code>")
@login_required
def support_thread(ticket_code):
    ticket = SupportTicket.query.filter_by(ticket_id=ticket_code).first_or_404()

    # authorize: owner by user_id or email match
    if not (ticket.user_id == current_user.id or ticket.email == current_user.email.lower() or getattr(current_user, "is_admin", False)):
        flash("You are not allowed to view this ticket.", "danger")
        return redirect(url_for("main.support"))

    page = max(int(request.args.get("page", 1)), 1)
    messages_page = (SupportMessage.query
                     .filter_by(ticket_id=ticket.id)
                     .order_by(SupportMessage.created_at.asc())
                     .paginate(page=page, per_page=20))
    # preload per-message attachments
    for m in messages_page.items:
        m.attachments = SupportAttachment.query.filter_by(message_id=m.id).all()

    return render_template("client/support_thread.html", ticket=ticket, messages_page=messages_page)

@main_bp.route("/support/t/<ticket_code>", methods=["POST"])
@login_required
def support_thread_post(ticket_code):
    ticket = SupportTicket.query.filter_by(ticket_id=ticket_code).first_or_404()

    if not (ticket.user_id == current_user.id or ticket.email == current_user.email.lower() or getattr(current_user, "is_admin", False)):
        flash("You are not allowed to reply to this ticket.", "danger")
        return redirect(url_for("main.support"))

    if ticket.status == "closed":
        flash("This ticket is closed.", "warning")
        return redirect(url_for("main.support_thread", ticket_code=ticket_code))

    body = (request.form.get("body") or "").strip()
    if len(body) < 2:
        flash("Message is too short.", "warning")
        return redirect(url_for("main.support_thread", ticket_code=ticket_code))

    msg = SupportMessage(
        ticket_id=ticket.id,
        author_user_id=current_user.id,
        author_role=("admin" if getattr(current_user, "is_admin", False) else "user"),
        body=body,
    )
    db.session.add(msg)
    db.session.flush()

    # attachments per message
    files = request.files.getlist("attachments")
    upload_base = os.path.join(current_app.instance_path, "support_uploads", datetime.utcnow().strftime("%Y%m%d"))
    os.makedirs(upload_base, exist_ok=True)
    for f in files[:MAX_FILES]:
        if not f or not f.filename: continue
        if not _allowed_file(f.filename): 
            flash(f"Unsupported file: {f.filename}", "info"); continue
        f.seek(0, os.SEEK_END); size = f.tell(); f.seek(0)
        if size > MAX_EACH_FILE_MB*1024*1024:
            flash(f"{f.filename} exceeds {MAX_EACH_FILE_MB}MB", "warning"); continue
        safe = secure_filename(f.filename)
        dest = os.path.join(upload_base, f"{uuid.uuid4().hex[:10]}-{safe}")
        f.save(dest)
        mime = mimetypes.guess_type(dest)[0] or "application/octet-stream"
        db.session.add(SupportAttachment(ticket_id=ticket.id, message_id=msg.id,
                                         filename=safe, path=dest, size_bytes=size, mime=mime))

    # auto-bump status from 'open' to 'pending' when user replies to admin
    if msg.author_role == "user" and ticket.status == "open":
        ticket.status = "pending"

    db.session.commit()

    # email notify support team on user reply; or notify user on admin reply
    try:
        if msg.author_role == "user":
            _email_support_alert(ticket)  # internal team
        else:
            _email_support_ack(ticket)    # ack to user (or write a different 'reply' template)
    except Exception as e:
        current_app.logger.warning(f"Support reply email failed: {e}")

    flash("Reply sent.", "success")
    return redirect(url_for("main.support_thread", ticket_code=ticket_code))

def _safe_redirect(default):
    ref = request.referrer
    if ref:
        u = urlparse(ref)
        if not u.netloc or u.netloc == request.host:  # same-origin only
            return ref
    return url_for(default)

@main_bp.route("/i18n/set", methods=["POST"], endpoint="set_language")
def set_language():
    lang = (request.form.get("lang") or "en").lower()
    supported = {"en", "fr", "de", "sw"}
    if lang not in supported:
        flash("Unsupported language.", "warning")
        return redirect(request.referrer or url_for("main.index"))

    session["lang"] = lang

    # optional: save on the user profile too
    if getattr(current_user, "is_authenticated", False):
        try:
            if getattr(current_user, "language", None) != lang:
                current_user.language = lang
                db.session.commit()
        except Exception as e:
            current_app.logger.warning(f"[i18n] user language persist failed: {e}")

    current_app.logger.info(f"[i18n] lang set -> {lang}")
    flash("Language updated.", "success")
    return redirect(_safe_redirect("main.index"))


@main_bp.route("/cookies/consent", methods=["POST"])
def cookies_consent():
    # expects form: analytics=on/off, marketing=on/off
    analytics = (request.form.get("analytics") == "on")
    marketing = (request.form.get("marketing") == "on")
    payload = {
        "essential": True,
        "analytics": bool(analytics),
        "marketing": bool(marketing),
        "ts": datetime.utcnow().isoformat() + "Z",
    }
    resp = make_response(redirect(request.referrer or url_for("main.index")))
    # persist ~ 1 year
    resp.set_cookie(
        "td.consent",
        json.dumps(payload, separators=(",", ":")),
        max_age=365*24*3600,
        secure=bool(current_app.config.get("SESSION_COOKIE_SECURE", False)),
        httponly=False,  # must be readable by client for UI; keep non-sensitive
        samesite="Lax",
    )
    flash("Your cookie preferences are saved.", "success")
    return resp

@main_bp.route("/cookies/withdraw", methods=["POST"])
def cookies_withdraw():
    resp = make_response(redirect(request.referrer or url_for("main.cookies")))
    resp.delete_cookie("td.consent")
    flash("Cookie preferences cleared.", "info")
    return resp
