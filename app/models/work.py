from ..extensions import db
from datetime import datetime


class WorkSubmission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey(
        'task_request.id'), nullable=False)
    by_user_id = db.Column(
        db.Integer, db.ForeignKey('user.id'), nullable=False)
    version = db.Column(db.Integer, default=1)
    comment = db.Column(db.Text)
    files_json = db.Column(db.Text)  # JSON list of FileAsset ids or names
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
