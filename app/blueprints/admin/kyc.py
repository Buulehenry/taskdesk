from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy import or_, func
from ...security import roles_required
from ...extensions import db
from ...models.user import User, KycSubmission
from ...services.email_service import send_email
from . import admin_bp

@admin_bp.post('/users/<int:user_id>/kyc/review')
@login_required
@roles_required('admin')
def kyc_review(user_id):
    action = (request.form.get('action') or '').strip().lower()  # approve|reject
    note   = request.form.get('note')
    sub_id = request.form.get('submission_id', type=int)
    nxt    = request.form.get('next') or request.referrer

    if action not in ('approve', 'reject'):
        flash('Invalid action.', 'warning')
        return redirect(nxt or url_for('admin.inbox'))

    user = User.query.get_or_404(user_id)

    if sub_id:
        sub = KycSubmission.query.get_or_404(sub_id)
        if sub.user_id != user.id:
            abort(400)
    else:
        sub = (
            KycSubmission.query
            .filter_by(user_id=user.id)
            .order_by(KycSubmission.submitted_at.desc())
            .first()
        )
        if not sub:
            abort(404)

    sub.status       = 'approved' if action == 'approve' else 'rejected'
    sub.review_note  = note
    sub.reviewed_by  = current_user.id
    sub.reviewed_at  = datetime.utcnow()

    if getattr(user, 'freelancer_profile', None):
        user.freelancer_profile.kyc_status     = sub.status
        user.freelancer_profile.kyc_checked_at = datetime.utcnow()

    db.session.commit()

    try:
        if user.email:
            send_email(
                to=user.email,
                subject=f"KYC {sub.status.title()}",
                template='kyc_result.html',
                user=user,
                submission=sub,
            )
    except Exception:
        pass

    flash(f'KYC {sub.status}.', 'success')
    return redirect(nxt or url_for('admin.user_detail', user_id=user.id))

@admin_bp.get('/kyc')
@login_required
@roles_required('admin')
def kyc_queue():
    q        = (request.args.get('q') or '').strip()
    status   = (request.args.get('status') or 'submitted').strip()
    page     = max(int(request.args.get('page', 1) or 1), 1)
    per_page = 20

    base = KycSubmission.query.order_by(KycSubmission.submitted_at.desc())

    if status in ('submitted', 'approved', 'rejected'):
        base = base.filter(KycSubmission.status == status)

    if q:
        like = f"%{q}%"
        base = (base.join(User, KycSubmission.user_id == User.id)
                    .filter(or_(
                        User.name.ilike(like),
                        User.email.ilike(like),
                        func.cast(User.id, db.String).ilike(like),
                        func.coalesce(KycSubmission.id_number, '').ilike(like),
                    )))

    total = base.count()
    pages = max((total + per_page - 1)//per_page, 1)
    page  = min(page, pages)
    subs  = base.offset((page-1)*per_page).limit(per_page).all()

    user_ids = {s.user_id for s in subs if s.user_id}
    users_map = {u.id: u for u in User.query.filter(User.id.in_(user_ids)).all()}

    return render_template('admin/kyc_queue.html',
                           subs=subs, users_map=users_map,
                           page=page, pages=pages, total=total, status=status, q=q)
