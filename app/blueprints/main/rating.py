from datetime import datetime, timedelta
from flask import request, redirect, url_for, flash, current_app
from flask_login import current_user
from app.extensions import db
from app.models.feedback import Rating

from . import main_bp

@main_bp.route("/rate", methods=["POST"], endpoint="rating_post")
def rating_post():
    # Basic validation
    try:
        stars = int(request.form.get("stars", "0"))
    except ValueError:
        stars = 0
    comment = (request.form.get("comment") or "").strip()
    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip()

    if stars < 1 or stars > 5:
        flash("Please select a rating between 1 and 5 stars.", "warning")
        return redirect(request.referrer or url_for("main.index"))

    if len(comment) > 2000:
        flash("Comment is too long.", "warning")
        return redirect(request.referrer or url_for("main.index"))

    # Spam throttle (by user or IP)
    window = int(current_app.config.get("RATING_THROTTLE_SECONDS", 60))
    since = datetime.utcnow() - timedelta(seconds=window)
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
    ua = (request.user_agent.string or "")[:300]

    qry = Rating.query.filter(Rating.created_at >= since)
    if current_user.is_authenticated:
        qry = qry.filter(Rating.user_id == current_user.id)
    else:
        qry = qry.filter(Rating.ip == ip)

    if qry.count() >= 1:
        flash("You’re sending feedback too quickly. Please try again shortly.", "warning")
        return redirect(request.referrer or url_for("main.index"))

    r = Rating(
        user_id=(current_user.id if current_user.is_authenticated else None),
        name=name or (getattr(current_user, "name", None) if current_user.is_authenticated else None),
        email=email or (getattr(current_user, "email", None) if current_user.is_authenticated else None),
        stars=stars,
        comment=comment or None,
        ip=ip[:64] if ip else None,
        user_agent=ua,
        is_public=True,      # visible by default; admins can hide
        is_deleted=False,
    )
    db.session.add(r)
    db.session.commit()
    flash("Thanks for your feedback!", "success")
    # Return to footer
    return redirect((request.referrer or url_for("main.index")) + "#rate")
