# app/models/task.py
from datetime import datetime
from ..extensions import db

class TaskRequest(db.Model):
    __tablename__ = 'task_request'

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)

    title = db.Column(db.String(200), nullable=False, index=True)
    category = db.Column(db.String(50), index=True)
    description = db.Column(db.Text)
    admin_notes = db.Column(db.Text) 

    deadline_at = db.Column(db.DateTime, index=True)
    client_budget = db.Column(db.Float)
    priority = db.Column(db.String(20), default="normal", index=True)   # normal|rush
    status = db.Column(db.String(30), default="submitted", index=True)  # submitted|quoted|...
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Client who created the task
    client = db.relationship(
        'User',
        foreign_keys=[client_id],
        backref=db.backref('client_tasks', lazy='selectin')
    )

    file_assets = db.relationship(
        'FileAsset',
        backref='task',
        lazy='selectin',
        cascade='all, delete-orphan'
    )

    # Assignments (normal collection; NOT dynamic) — pairs with Assignment.task
    assignments = db.relationship(
        'Assignment',
        back_populates='task',
        lazy='selectin',
        cascade='all, delete-orphan'
    )

    # Quotes (use back_populates to avoid backref collisions with Quote.task)
    quotes = db.relationship(
        'Quote',
        back_populates='task',
        lazy='selectin',
        cascade='all, delete-orphan'
    )
