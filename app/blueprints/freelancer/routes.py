# app/blueprints/freelancer/routes.py
from datetime import datetime
from typing import Optional

from flask import render_template, redirect, url_for, flash, abort, request
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload

from ...extensions import db
from ...models.assignment import Assignment
from ...models.task import TaskRequest
from ...models.user import (
    User,
    KycSubmission,
    FreelancerExperience,
    FreelancerEducation,
)
from ...services.email_service import send_email
from ...services.storage_service import save_upload, allowed_ext
from ...models.fileasset import FileAsset
from ...models.work import WorkSubmission

from . import freelancer_bp


# -----------------
# Dashboard
# -----------------
# ---- small helpers ----
def _parse_date(val: str):
    if not val:
        return None
    try:
        return datetime.strptime(val, "%Y-%m-%d").date()
    except ValueError:
        return None

def _to_int(val):
    try:
        return int(val) if str(val).strip() else None
    except (TypeError, ValueError):
        return None
    
@freelancer_bp.route('/dashboard')
@login_required
def dashboard():
    assigns = (
        Assignment.query
        .options(joinedload(Assignment.task))
        .filter_by(assignee_id=current_user.id)
        .order_by(Assignment.id.desc())
        .all()
    )
    return render_template('freelancer/dashboard.html', assignments=assigns)


# -----------------
# Assignment Accept / Decline
# -----------------

@freelancer_bp.route('/assignments/<int:assignment_id>/accept')
@login_required
def assignment_accept(assignment_id):
    a = Assignment.query.get_or_404(assignment_id)

    if a.assignee_id != current_user.id:
        flash('Not your assignment.', 'danger')
        return redirect(url_for('freelancer.dashboard'))

    if a.status not in ('pending', 'pending_accept'):
        flash('Assignment is not pending.', 'warning')
        return redirect(url_for('freelancer.dashboard'))

    if a.accept_expires_at and datetime.utcnow() > a.accept_expires_at:
        a.status = 'expired'
        db.session.commit()
        flash('Assignment expired.', 'warning')
        return redirect(url_for('freelancer.dashboard'))

    # Accept
    a.status = 'accepted'
    a.accepted_at = datetime.utcnow()

    # Ensure related task moves to in_progress
    t = TaskRequest.query.get(a.task_id)
    if t and t.status in ('quoted', 'submitted', 'pending_accept', 'awaiting_quote'):
        t.status = 'in_progress'

    db.session.commit()

    # Notify admin (simple: first admin)
    admin = User.query.filter_by(role='admin').first()
    if admin and t:
        try:
            send_email(
                to=admin.email,
                subject=f"Assignment accepted — Task #{t.id}",
                template='email/assignment_status_admin.html',
                assignment=a, task=t, assignee=current_user
            )
        except Exception:
            pass

    flash('Assignment accepted. You can start work.', 'success')
    return redirect(url_for('freelancer.dashboard'))


@freelancer_bp.route('/assignments/<int:assignment_id>/decline')
@login_required
def assignment_decline(assignment_id):
    a = Assignment.query.get_or_404(assignment_id)

    if a.assignee_id != current_user.id:
        flash('Not your assignment.', 'danger')
        return redirect(url_for('freelancer.dashboard'))

    if a.status not in ('pending', 'pending_accept'):
        flash('Assignment is not pending.', 'warning')
        return redirect(url_for('freelancer.dashboard'))

    a.status = 'declined'
    a.declined_at = datetime.utcnow()
    db.session.commit()

    # Notify admin
    t = TaskRequest.query.get(a.task_id)
    admin = User.query.filter_by(role='admin').first()
    if admin and t:
        try:
            send_email(
                to=admin.email,
                subject=f"Assignment declined — Task #{t.id}",
                template='email/assignment_status_admin.html',
                assignment=a, task=t, assignee=current_user
            )
        except Exception:
            pass

    flash('Assignment declined.', 'info')
    return redirect(url_for('freelancer.dashboard'))


# -----------------
# Submit Work (files + comment)
# -----------------

@freelancer_bp.route('/tasks/<int:task_id>/submit', methods=['GET', 'POST'])
@login_required
def submit_work(task_id):
    # Verify assignment ownership
    a = Assignment.query.filter_by(task_id=task_id, assignee_id=current_user.id).first()
    if not a or a.status not in ('accepted', 'pending'):
        flash('You are not assigned to this task.', 'danger')
        return redirect(url_for('freelancer.dashboard'))

    if request.method == 'POST':
        files = request.files.getlist('files')
        saved_ids = []
        for f in files:
            if not f or not f.filename:
                continue
            if not allowed_ext(f.filename):
                flash(f'Skipped unsupported file: {f.filename}', 'info')
                continue
            stored = save_upload(f, subdir=f"freelancer/{current_user.id}/tasks/{task_id}")
            asset = FileAsset(
                owner_id=current_user.id,
                task_id=task_id,
                path=stored,
                kind='work',
                filename=f.filename,
                mime=f.mimetype,
                size_bytes=getattr(f, 'content_length', None)
            )
            db.session.add(asset)
            db.session.flush()
            saved_ids.append(asset.id)

        ws = WorkSubmission(
            task_id=task_id,
            by_user_id=current_user.id,
            comment=request.form.get('comment'),
            files_json=str(saved_ids)
        )
        db.session.add(ws)

        # Nudge task status to review if appropriate
        t = TaskRequest.query.get(task_id)
        if t and t.status == 'in_progress':
            t.status = 'review'

        db.session.commit()
        flash('Work submitted.', 'success')
        return redirect(url_for('freelancer.dashboard'))

    t = TaskRequest.query.get_or_404(task_id)
    return render_template('freelancer/submit.html', task=t)


# -----------------
# Profile & Evidence
# -----------------


@freelancer_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if current_user.role != 'freelancer':
        flash('Only freelancers can edit freelancer profiles.', 'warning')
        return redirect(url_for('client.dashboard'))

    # Basic profile fields submit (if you have them in the template)
    if request.method == 'POST':
        fp = current_user.freelancer_profile
        if not fp:
            flash('Freelancer profile not found.', 'danger')
            return redirect(url_for('freelancer.profile'))
        fp.headline = (request.form.get('headline') or '')[:160]
        fp.bio = request.form.get('bio')
        fp.skills = request.form.get('skills')
        fp.location = request.form.get('location')
        fp.portfolio_url = request.form.get('portfolio_url')
        fp.payout_email = request.form.get('payout_email')
        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('freelancer.profile'))

    # GET
    exps = (FreelancerExperience.query
            .filter_by(user_id=current_user.id)
            .order_by(FreelancerExperience.start_date.desc().nullslast())
            .all())
    edus = (FreelancerEducation.query
            .filter_by(user_id=current_user.id)
            .order_by(FreelancerEducation.end_year.desc().nullslast())
            .all())
    resumes = (FileAsset.query
               .filter_by(owner_id=current_user.id, kind='resume')
               .order_by(FileAsset.uploaded_at.desc())
               .all())
    kyc = (KycSubmission.query
           .filter_by(user_id=current_user.id)
           .order_by(KycSubmission.submitted_at.desc())
           .first())
    return render_template('freelancer/profile.html',
                           exps=exps, edus=edus, resumes=resumes, kyc=kyc)


# -------- Experience CRUD --------

@freelancer_bp.post('/experience/new')
@login_required
def exp_create():
    e = FreelancerExperience(
        user_id=current_user.id,
        title=request.form['title'],
        company=request.form.get('company'),
        start_date=_parse_date(request.form.get('start_date')),
        end_date=_parse_date(request.form.get('end_date')),
        summary=request.form.get('summary'),
        skills=request.form.get('skills'),
    )
    db.session.add(e)
    db.session.commit()
    flash('Experience added.', 'success')
    return redirect(url_for('freelancer.profile'))


@freelancer_bp.post('/experience/<int:exp_id>/edit')
@login_required
def exp_edit(exp_id):
    e = FreelancerExperience.query.get_or_404(exp_id)
    if e.user_id != current_user.id:
        abort(403)
    e.title = request.form['title']
    e.company = request.form.get('company')
    e.start_date = _parse_date(request.form.get('start_date'))
    e.end_date = _parse_date(request.form.get('end_date'))
    e.summary = request.form.get('summary')
    e.skills = request.form.get('skills')
    db.session.commit()
    flash('Experience updated.', 'success')
    return redirect(url_for('freelancer.profile'))


@freelancer_bp.post('/experience/<int:exp_id>/delete')
@login_required
def exp_delete(exp_id):
    e = FreelancerExperience.query.get_or_404(exp_id)
    if e.user_id != current_user.id:
        abort(403)
    db.session.delete(e)
    db.session.commit()
    flash('Experience removed.', 'success')
    return redirect(url_for('freelancer.profile'))


# -------- Education CRUD --------

@freelancer_bp.post('/education/new')
@login_required
def edu_create():
    ed = FreelancerEducation(
        user_id=current_user.id,
        school=request.form.get('school'),
        degree=request.form.get('degree'),
        field=request.form.get('field'),
        start_year=_to_int(request.form.get('start_year')),
        end_year=_to_int(request.form.get('end_year')),
        notes=request.form.get('notes')
    )
    db.session.add(ed)
    db.session.commit()
    flash('Education added.', 'success')
    return redirect(url_for('freelancer.profile'))


@freelancer_bp.post('/education/<int:edu_id>/delete')
@login_required
def edu_delete(edu_id):
    ed = FreelancerEducation.query.get_or_404(edu_id)
    if ed.user_id != current_user.id:
        abort(403)
    db.session.delete(ed)
    db.session.commit()
    flash('Education removed.', 'success')
    return redirect(url_for('freelancer.profile'))

# -----------------
# KYC
# -----------------

@freelancer_bp.route('/kyc', methods=['GET', 'POST'])
@login_required
def kyc():
    if current_user.role != 'freelancer':
        abort(403)

    if request.method == 'POST':
        doc_type = request.form.get('doc_type')
        id_number = request.form.get('id_number')
        country = request.form.get('country')

        front_id = None
        back_id = None
        selfie_id = None

        f_front = request.files.get('kyc_id_front')
        f_back = request.files.get('kyc_id_back')
        f_selfie = request.files.get('kyc_selfie')

        if f_front and f_front.filename:
            p = save_upload(f_front, subdir=f"freelancer/{current_user.id}/kyc")
            fa = FileAsset(owner_id=current_user.id, path=p, filename=f_front.filename, mime=f_front.mimetype)
            db.session.add(fa); db.session.flush(); front_id = fa.id
        if f_back and f_back.filename:
            p = save_upload(f_back, subdir=f"freelancer/{current_user.id}/kyc")
            fa = FileAsset(owner_id=current_user.id, path=p, filename=f_back.filename, mime=f_back.mimetype)
            db.session.add(fa); db.session.flush(); back_id = fa.id
        if f_selfie and f_selfie.filename:
            p = save_upload(f_selfie, subdir=f"freelancer/{current_user.id}/kyc")
            fa = FileAsset(owner_id=current_user.id, path=p, filename=f_selfie.filename, mime=f_selfie.mimetype)
            db.session.add(fa); db.session.flush(); selfie_id = fa.id

        sub = KycSubmission(
            user_id=current_user.id,
            doc_type=doc_type,
            id_number=id_number,
            country=country,
            file_id_front=front_id,
            file_id_back=back_id,
            file_id_selfie=selfie_id,
        )
        db.session.add(sub)

        # Mirror status on profile for quick checks
        if current_user.freelancer_profile:
            current_user.freelancer_profile.kyc_status = 'submitted'
        db.session.commit()

        # TODO: email notify admin & user if you have templates ready
        flash('KYC submitted. We will review shortly.', 'success')
        return redirect(url_for('freelancer.profile'))

    return render_template('freelancer/kyc.html')
