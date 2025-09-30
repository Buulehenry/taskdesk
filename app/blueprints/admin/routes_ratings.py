from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required
from ...security import roles_required
from app.extensions import db
from app.models.feedback import Rating
from sqlalchemy import desc

from . import admin_bp

@admin_bp.route("/ratings")
@login_required
@roles_required('admin')
def ratings_list():
    q = (request.args.get("q") or "").strip()
    vis = (request.args.get("vis") or "").strip()   # public / hidden / deleted / all
    page = max(int(request.args.get("page", 1)), 1)

    qry = Rating.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(db.or_(Rating.comment.ilike(like),
                                Rating.name.ilike(like),
                                Rating.email.ilike(like)))
    if vis == "public":
        qry = qry.filter(Rating.is_deleted.is_(False), Rating.is_public.is_(True))
    elif vis == "hidden":
        qry = qry.filter(Rating.is_deleted.is_(False), Rating.is_public.is_(False))
    elif vis == "deleted":
        qry = qry.filter(Rating.is_deleted.is_(True))
    else:
        qry = qry.filter(Rating.is_deleted.is_(False))  # default exclude deleted

    ratings = qry.order_by(desc(Rating.created_at)).paginate(page=page, per_page=30)
    return render_template("admin/ratings_list.html", ratings=ratings)

@admin_bp.route("/ratings/<int:rid>/hide", methods=["POST"])
@login_required
@roles_required('admin')
def ratings_hide(rid):
    r = Rating.query.get_or_404(rid)
    r.is_public = False
    db.session.commit()
    flash("Rating hidden.", "success")
    return redirect(request.referrer or url_for("admin.ratings_list"))

@admin_bp.route("/ratings/<int:rid>/unhide", methods=["POST"])
@login_required
@roles_required('admin')
def ratings_unhide(rid):
    r = Rating.query.get_or_404(rid)
    r.is_public = True
    db.session.commit()
    flash("Rating made public.", "success")
    return redirect(request.referrer or url_for("admin.ratings_list"))

@admin_bp.route("/ratings/<int:rid>/delete", methods=["POST"])
@login_required
@roles_required('admin')
def ratings_delete(rid):
    r = Rating.query.get_or_404(rid)
    r.is_deleted = True
    db.session.commit()
    flash("Rating deleted.", "success")
    return redirect(request.referrer or url_for("admin.ratings_list"))

@admin_bp.route("/ratings/<int:rid>/restore", methods=["POST"])
@login_required
@roles_required('admin')
def ratings_restore(rid):
    r = Rating.query.get_or_404(rid)
    r.is_deleted = False
    db.session.commit()
    flash("Rating restored.", "success")
    return redirect(request.referrer or url_for("admin.ratings_list"))
