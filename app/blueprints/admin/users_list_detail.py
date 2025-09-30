from flask import render_template, request
from flask_login import login_required
from sqlalchemy import or_, asc, desc, func
from ...security import roles_required
from ...extensions import db
from ...models.user import User
from . import admin_bp

@admin_bp.get('/users')
@login_required
@roles_required('admin')
def users_list():
    q        = (request.args.get('q') or '').strip()
    role     = (request.args.get('role') or '').strip()
    status   = (request.args.get('status') or '').strip()
    vetted   = (request.args.get('vetted') or '').strip()
    sort     = request.args.get('sort', '-created').strip()
    page     = max(int(request.args.get('page', 1) or 1), 1)
    per_page = 20

    base = User.query

    if q:
        like = f"%{q}%"
        base = base.filter(or_(User.name.ilike(like), User.email.ilike(like), User.phone.ilike(like)))

    if role:
        base = base.filter(User.role == role)

    if status == 'active':
        base = base.filter(User.deleted_at.is_(None), User.status == 'active')
    elif status == 'suspended':
        base = base.filter(User.status == 'suspended')
    elif status == 'deleted':
        base = base.filter(User.deleted_at.isnot(None))
    elif status == 'unverified':
        base = base.filter(User.is_email_verified.is_(False))

    if vetted:
        base = base.filter(User.vetted_status == vetted)

    if sort == 'created':
        base = base.order_by(asc(User.created_at))
    elif sort == '-created':
        base = base.order_by(desc(User.created_at))
    elif sort == 'last_login':
        base = base.order_by(asc(User.last_login_at))
    elif sort == '-last_login':
        base = base.order_by(desc(User.last_login_at))
    elif sort == 'name':
        base = base.order_by(asc(User.name))
    else:
        base = base.order_by(desc(User.created_at))

    total = base.count()
    pages = max((total + per_page - 1) // per_page, 1)
    page = min(page, pages)
    users = base.offset((page - 1) * per_page).limit(per_page).all()

    counts = {
        'all': total,
        'client': User.query.filter_by(role='client').count(),
        'freelancer': User.query.filter_by(role='freelancer').count(),
        'admin': User.query.filter_by(role='admin').count(),
        'suspended': User.query.filter(User.status == 'suspended').count(),
        'deleted': User.query.filter(User.deleted_at.isnot(None)).count(),
    }
    return render_template('admin/users_list.html', users=users, page=page, pages=pages, counts=counts, users_total=total)

@admin_bp.get('/users/<int:user_id>')
@login_required
@roles_required('admin')
def user_detail(user_id):
    u = User.query.get_or_404(user_id)
    stats = {
        'tasks_count': getattr(u, 'tasks_count', None),
        'assignments_count': getattr(u, 'assignments_count', None),
        'invoices_count': getattr(u, 'invoices_count', None),
        'last_active_at': u.last_login_at,
    }
    tasks = getattr(u, 'tasks_created', [])[:10]
    assignments = getattr(u, 'assignments', [])[:10]
    invoices = getattr(u, 'invoices', [])[:10]
    return render_template('admin/user_detail.html', user=u, stats=stats, tasks=tasks, assignments=assignments, invoices=invoices)
