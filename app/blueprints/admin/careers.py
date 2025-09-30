import os, mimetypes
from flask import render_template, request, redirect, url_for, flash, send_file, abort, current_app
from flask_login import login_required
from ...security import roles_required
from app.extensions import db
from app.models.careers import JobPosting, JobApplication
from sqlalchemy import desc

from . import admin_bp

@admin_bp.route("/careers")
@login_required
@roles_required('admin')
def careers_list():
    jobs = JobPosting.query.order_by(desc(JobPosting.created_at)).all()
    return render_template("admin/careers_list.html", jobs=jobs)

@admin_bp.route("/careers/new", methods=["GET","POST"])
@login_required
@roles_required('admin')
def careers_new():
    if request.method == "GET":
        return render_template("admin/careers_edit.html", job=None)
    title = (request.form.get("title") or "").strip()
    if not title:
        flash("Title required.", "warning")
        return redirect(url_for("admin.careers_new"))
    job = JobPosting(
        title=title,
        location=(request.form.get("location") or "").strip() or None,
        department=(request.form.get("department") or "").strip() or None,
        employment_type=(request.form.get("employment_type") or "").strip() or None,
        description_md=(request.form.get("description_md") or "").strip(),
        is_active=(request.form.get("is_active") == "on"),
    )
    db.session.add(job); db.session.commit()
    flash("Job created.", "success")
    return redirect(url_for("admin.careers_list"))

@admin_bp.route("/careers/<int:jid>/edit", methods=["GET","POST"])
@login_required
@roles_required('admin')
def careers_edit(jid):
    job = JobPosting.query.get_or_404(jid)
    if request.method == "GET":
        return render_template("admin/careers_edit.html", job=job)
    job.title = (request.form.get("title") or "").strip()
    job.location = (request.form.get("location") or "").strip() or None
    job.department = (request.form.get("department") or "").strip() or None
    job.employment_type = (request.form.get("employment_type") or "").strip() or None
    job.description_md = (request.form.get("description_md") or "").strip()
    job.is_active = (request.form.get("is_active") == "on")
    db.session.commit()
    flash("Job updated.", "success")
    return redirect(url_for("admin.careers_list"))

@admin_bp.route("/careers/<int:jid>/toggle", methods=["POST"])
@login_required
@roles_required('admin')
def careers_toggle(jid):
    job = JobPosting.query.get_or_404(jid)
    job.is_active = not job.is_active
    db.session.commit()
    flash("Visibility updated.", "success")
    return redirect(url_for("admin.careers_list"))

@admin_bp.route("/careers/<int:jid>/delete", methods=["POST"])
@login_required
@roles_required('admin')
def careers_delete(jid):
    job = JobPosting.query.get_or_404(jid)
    db.session.delete(job)
    db.session.commit()
    flash("Job deleted.", "success")
    return redirect(url_for("admin.careers_list"))

@admin_bp.route("/careers/<int:jid>/applications")
@login_required
@roles_required('admin')
def careers_apps(jid):
    job = JobPosting.query.get_or_404(jid)
    apps = job.applications.order_by(JobApplication.created_at.desc()).all()
    return render_template("admin/careers_apps.html", job=job, apps=apps)

@admin_bp.route("/careers/applications/<int:aid>/resume")
@login_required
@roles_required('admin')
def careers_resume(aid):
    a = JobApplication.query.get_or_404(aid)
    if not a.resume_path or not os.path.isfile(a.resume_path):
        abort(404)

    # Lock downloads to instance/resumes directory
    resumes_root = os.path.realpath(os.path.join(current_app.instance_path, "resumes"))
    real_path = os.path.realpath(a.resume_path)
    if not real_path.startswith(resumes_root + os.sep):
        # path traversal or outside allowed dir
        abort(403)

    mime = mimetypes.guess_type(real_path)[0] or "application/octet-stream"
    return send_file(
        real_path,
        mimetype=mime,
        as_attachment=True,
        download_name=a.resume_filename or os.path.basename(real_path),
        max_age=0,
        conditional=True,
        etag=True,
        last_modified=None,
    )