from flask import render_template, request, redirect, url_for, flash, current_app
from werkzeug.utils import secure_filename
from datetime import datetime
import os, uuid, mimetypes

from app.models.careers import JobPosting, JobApplication
from app.extensions import db, csrf

from . import main_bp

@main_bp.route("/about")
def about():
    return render_template("about.html")

@main_bp.route("/cookies")
def cookies():
    return render_template("cookies.html")

@main_bp.route("/careers")
def careers():
    q = (request.args.get("q") or "").strip()
    dept = (request.args.get("department") or "").strip()
    qry = JobPosting.query.filter(JobPosting.is_active.is_(True))
    if q:
        like = f"%{q}%"
        qry = qry.filter(db.or_(JobPosting.title.ilike(like),
                                JobPosting.department.ilike(like),
                                JobPosting.location.ilike(like)))
    if dept:
        qry = qry.filter(JobPosting.department.ilike(dept))
    jobs = qry.order_by(JobPosting.created_at.desc()).all()
    return render_template("careers.html", jobs=jobs)

@main_bp.route("/careers/<int:job_id>")
def career_detail(job_id):
    job = JobPosting.query.get_or_404(job_id)
    if not job.is_active:
        flash("This position is no longer accepting applications.", "warning")
    return render_template("career_detail.html", job=job)

@main_bp.route("/careers/<int:job_id>/apply", methods=["POST"])
def career_apply(job_id):
    job = JobPosting.query.get_or_404(job_id)
    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    cover = (request.form.get("cover_letter") or "").strip()
    if not name or "@" not in email:
        flash("Please enter your name and a valid email.", "warning")
        return redirect(url_for("main.career_detail", job_id=job_id))

    # upload resume (pdf/doc/docx only)
    f = request.files.get("resume")
    path = filename = None
    if f and f.filename:
        safe = secure_filename(f.filename)
        ext = (os.path.splitext(safe)[1] or "").lower()
        if ext not in {".pdf", ".doc", ".docx"}:
            flash("Resume must be PDF, DOC, or DOCX.", "warning")
            return redirect(url_for("main.career_detail", job_id=job_id))
        base = os.path.join(current_app.instance_path, "resumes", datetime.utcnow().strftime("%Y%m%d"))
        os.makedirs(base, exist_ok=True)
        fn = f"{uuid.uuid4().hex}{ext}"
        path = os.path.join(base, fn)
        f.save(path)
        filename = safe

    app = JobApplication(job_id=job.id, name=name, email=email, phone=phone,
                         cover_letter=cover or None, resume_path=path, resume_filename=filename)
    db.session.add(app); db.session.commit()

    flash("Application received. Thank you!", "success")
    return redirect(url_for("main.career_detail", job_id=job_id))
