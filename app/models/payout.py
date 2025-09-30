from datetime import datetime
from ..extensions import db


class Payout(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey(
        'task_request.id'), nullable=False)
    freelancer_id = db.Column(
        db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default='USD')
    # pending|queued|paid|failed
    status = db.Column(db.String(20), default='pending')
    scheduled_at = db.Column(db.DateTime)
    paid_at = db.Column(db.DateTime)
    method = db.Column(db.String(50))
    notes = db.Column(db.Text)
