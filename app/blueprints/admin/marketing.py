# app/blueprints/admin/marketing.py (or add to existing admin routes)
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, Response
from flask_login import login_required, current_user
from ...security import roles_required
from app.extensions import db, mail
from app.models.marketing import Subscriber, EmailCampaign
from app.models.user import User  # your user model
from sqlalchemy import func
from datetime import datetime
from flask_mail import Message

from . import admin_bp

def admin_guard():
    return current_user.is_authenticated and getattr(current_user, "is_admin", False)

@admin_bp.before_request
@login_required
@roles_required('admin')
def _guard():
    pass

# ---- Subscribers ----
@admin_bp.route("/subscribers")
def subscribers_list():
    q = (request.args.get("q") or "").strip().lower()
    status = request.args.get("status", "")
    page = max(int(request.args.get("page", 1)), 1)

    qry = Subscriber.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(db.or_(Subscriber.email.ilike(like), Subscriber.name.ilike(like), Subscriber.source.ilike(like)))
    if status == "active":
        qry = qry.filter(Subscriber.is_active.is_(True))
    elif status == "inactive":
        qry = qry.filter(Subscriber.is_active.is_(False))

    subs = qry.order_by(Subscriber.created_at.desc()).paginate(page=page, per_page=25)
    return render_template("admin/subscribers_list.html", subs=subs)

@admin_bp.route("/subscribers/export.csv")
def subscribers_export_csv():
    rows = Subscriber.query.order_by(Subscriber.created_at.desc()).all()
    def gen():
        yield "email,name,is_active,source,created_at\n"
        for s in rows:
            yield f"{s.email},{(s.name or '').replace(',',' ')},{1 if s.is_active else 0},{s.source or ''},{s.created_at.isoformat()}Z\n"
    return Response(gen(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=subscribers.csv"})

# ---- Campaigns ----
@admin_bp.route("/campaigns")
def campaigns_list():
    page = max(int(request.args.get("page", 1)), 1)
    camps = EmailCampaign.query.order_by(EmailCampaign.created_at.desc()).paginate(page=page, per_page=20)
    return render_template("admin/campaigns_list.html", camps=camps)

@admin_bp.route("/campaigns/new", methods=["GET", "POST"])
def campaigns_new():
    if request.method == "GET":
        return render_template("admin/campaigns_new.html")

    # POST
    title = (request.form.get("title") or "").strip()
    subject = (request.form.get("subject") or "").strip()
    segment = (request.form.get("segment") or "subscribers").strip()
    body_text = (request.form.get("body_text") or "").strip()
    body_html = (request.form.get("body_html") or "").strip()

    if not title or not subject or not (body_text or body_html):
        flash("Title, Subject and Body are required.", "warning")
        return redirect(url_for("admin.campaigns_new"))

    camp = EmailCampaign(
        title=title,
        subject=subject,
        segment=segment,
        body_text=body_text or None,
        body_html=body_html or None,
        created_by=getattr(current_user, "id", None),
    )
    db.session.add(camp)
    db.session.commit()
    flash("Campaign created.", "success")
    return redirect(url_for("admin.campaigns_list"))


@admin_bp.route("/campaigns/<int:cid>/send", methods=["POST"])
def campaigns_send(cid):
    camp = EmailCampaign.query.get_or_404(cid)
    if camp.sent_at:
        flash("Campaign already sent.", "info")
        return redirect(url_for("admin.campaigns_list"))

    # Build recipient list(s)
    subs = []
    users = []
    if camp.segment in ("subscribers", "both"):
        subs = (Subscriber.query
                .filter(Subscriber.is_active.is_(True))
                .with_entities(Subscriber.email, Subscriber.token, Subscriber.name)
                .all())
    if camp.segment in ("users", "both"):
        users = User.query.with_entities(User.email, User.name).all()

    # dedupe by email, but keep token if exists (for unsubscribe)
    seen = set()
    recipients = []
    for e, tok, nm in subs:
        if e and "@" in e and e not in seen:
            recipients.append(("subscriber", e, nm, tok))
            seen.add(e)
    for e, nm in users:
        if e and "@" in e and e not in seen:
            recipients.append(("user", e, nm, None))
            seen.add(e)

    # ---- Defaults used in replacements
    base = current_app.config.get("EXTERNAL_BASE_URL", "http://localhost:5000")
    sender = (current_app.config.get("MAIL_DEFAULT_SENDER_NAME", "TaskDesk"),
              current_app.config.get("MAIL_DEFAULT_SENDER", "no-reply@taskdesk.example"))
    default_cta_label = "Open TaskDesk"
    default_cta_url = base

    sent = 0
    for kind, email, nm, tok in recipients:
        if "mail" not in current_app.extensions:
            current_app.logger.info(f"[campaign stub] {email}")
            sent += 1
            continue

        # per-recipient unsubscribe bits
        unsub_html = unsub_text = ""
        link = ""
        if kind == "subscriber" and tok:
            link = f"{base}/unsubscribe/{tok}"
            unsub_text = f"\n\n—\nTo unsubscribe, visit: {link}\n"
            unsub_html = f"<hr><p style='font-size:12px;color:#666'>To unsubscribe, <a href='{link}'>click here</a>.</p>"

        # ---- Simple token replacement (PUT THIS RIGHT HERE)
        person_name = (nm or "there")
        body_text = (camp.body_text or "")
        body_html = (camp.body_html or "")

        body_text = (body_text
                     .replace("{{name}}", person_name)
                     .replace("{{cta_label}}", default_cta_label)
                     .replace("{{cta_url}}", default_cta_url)
                     .replace("{{unsub_url}}", link)) + unsub_text

        body_html = (body_html
                     .replace("{{name}}", person_name)
                     .replace("{{cta_label}}", default_cta_label)
                     .replace("{{cta_url}}", default_cta_url)
                     .replace("{{unsub_url}}", link)) + unsub_html
        # ---- end replacements

        msg = Message(subject=camp.subject, sender=sender, recipients=[email],
                      body=body_text or None, html=body_html or None)
        try:
            mail.send(msg)
            sent += 1
        except Exception as e:
            current_app.logger.warning(f"send fail {email}: {e}")

    camp.sent_at = datetime.utcnow()
    db.session.commit()
    flash(f"Campaign sent to {sent} recipients.", "success")
    return redirect(url_for("admin.campaigns_list"))
