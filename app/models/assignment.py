from datetime import datetime
from ..extensions import db

class Assignment(db.Model):
    __tablename__ = "assignment"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('task_request.id'), nullable=False, index=True)
    assignee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    assigned_by = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)

    status = db.Column(db.String(20), default='pending', index=True)  # pending|pending_accept|accepted|declined|expired|revoked
    accept_expires_at = db.Column(db.DateTime)
    accepted_at = db.Column(db.DateTime)
    declined_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    task     = db.relationship('TaskRequest', back_populates='assignments')
    assignee = db.relationship('User', foreign_keys=[assignee_id],
                               backref=db.backref('assignments_assignee', lazy='selectin'))
    assigner = db.relationship('User', foreign_keys=[assigned_by],
                               backref=db.backref('assignments_created', lazy='selectin'))
