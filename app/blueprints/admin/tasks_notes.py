from flask import request, redirect, url_for, flash
from flask_login import login_required
from ...security import roles_required
from ...extensions import db
from ...models.task import TaskRequest
from . import admin_bp

@admin_bp.post('/tasks/<int:task_id>/notes')
@login_required
@roles_required('admin')
def task_notes_save(task_id):
    t = TaskRequest.query.get_or_404(task_id)
    notes = (request.form.get('notes') or '').strip()
    # Ensure your TaskRequest has admin_notes column
    t.admin_notes = notes
    db.session.commit()
    flash('Notes saved.', 'success')
    return redirect(url_for('admin.task_triage', task_id=t.id))
