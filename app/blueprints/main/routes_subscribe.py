from flask import request, redirect, url_for, flash, current_app, render_template
from sqlalchemy import func
from app.models.marketing import Subscriber
from datetime import datetime, timedelta
from app.extensions import db
from flask_mail import Message
from app.extensions import mail

from . import main_bp

# basic throttle: 5 requests / 10 minutes per IP/email
SUB_THROTTLE_MAX = 5
SUB_THROTTLE_WINDOW_MIN = 10

def _client_ip():
    h = request.headers.get("X-Forwarded-For")
    return (h.split(",")[0].strip() if h else request.remote_addr) or "0.0.0.0"

@main_bp.route("/subscribe", methods=["GET"])
def subscribe_form():
    return render_template("subscribe.html")  # optional standalone page
    # If you only use the footer form, you can skip this view/template.

@main_bp.route("/subscribe", methods=["POST"])
def subscribe_post():
    email = (request.form.get("email") or "").strip().lower()
    name = (request.form.get("name") or "").strip() or None
    source = (request.form.get("source") or "footer").strip()

    if not email or "@" not in email:
        flash("Please enter a valid email.", "warning")
        return redirect(request.referrer or url_for("main.index"))

    # throttle
    window_start = datetime.utcnow() - timedelta(minutes=SUB_THROTTLE_WINDOW_MIN)
    recent = Subscriber.query.filter(
        Subscriber.created_at >= window_start,
        Subscriber.email == email
    ).count()
    if recent >= SUB_THROTTLE_MAX:
        flash("Please try again later.", "info")
        return redirect(request.referrer or url_for("main.index"))

    sub = Subscriber.query.filter_by(email=email).first()
    if sub:
        if not sub.is_active:
            sub.is_active = True
            sub.unsubscribed_at = None
            sub.updated_at = datetime.utcnow()
        if name and not sub.name:
            sub.name = name
    else:
        sub = Subscriber(email=email, name=name, source=source, is_active=True)
        db.session.add(sub)

    db.session.commit()

    # send welcome/confirmation (optional)
    try:
        _send_subscribe_receipt(sub)
    except Exception as e:
        current_app.logger.info(f"Subscribe email failed: {e}")

    flash("Thanks! You're subscribed.", "success")
    # send user back to where they clicked (footer)
    return redirect(request.referrer or url_for("main.index"))

def _send_subscribe_receipt(sub: Subscriber):
    if "mail" not in current_app.extensions:  # graceful fallback
        current_app.logger.info(f"[subscribe] receipt -> {sub.email}")
        return
    sender = (current_app.config.get("MAIL_DEFAULT_SENDER_NAME", "TaskDesk"),
              current_app.config.get("MAIL_DEFAULT_SENDER"))
    base = current_app.config.get("EXTERNAL_BASE_URL")
    unsub = f"{base}/unsubscribe/{sub.token}"

    body_text = (f"Hi {sub.name or ''}\n\nThanks for subscribing to TaskDesk updates.\n"
                 f"If this wasn't you or you want to stop, unsubscribe here: {unsub}\n")
    body_html = (f"<p>Hi {sub.name or ''}</p>"
                 f"<p>Thanks for subscribing to <strong>TaskDesk</strong> updates.</p>"
                 f"<p style='font-size:12px;color:#666'>"
                 f"If this wasn’t you or you want to stop, "
                 f"<a href='{unsub}'>unsubscribe</a>.</p>")

    msg = Message(subject="You're subscribed — TaskDesk",
                  sender=sender, recipients=[sub.email],
                  body=body_text, html=body_html)
    mail.send(msg)

@main_bp.route("/unsubscribe/<token>", methods=["GET"])
def unsubscribe(token):
    sub = Subscriber.query.filter_by(token=token).first_or_404()
    sub.is_active = False
    sub.unsubscribed_at = datetime.utcnow()
    db.session.commit()
    flash("You’ve been unsubscribed. Sorry to see you go!", "info")
    return redirect(url_for("main.index"))
