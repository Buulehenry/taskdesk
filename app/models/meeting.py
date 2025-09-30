# app/models/meeting.py
from datetime import datetime
from ..extensions import db

class Meeting(db.Model):
    __tablename__ = "meeting"

    id = db.Column(db.Integer, primary_key=True)

    # Task relationship
    task_id = db.Column(db.Integer, db.ForeignKey("task_request.id", ondelete="CASCADE"), nullable=False, index=True)
    task = db.relationship(
        "TaskRequest",
        backref=db.backref("meetings", lazy="selectin", cascade="all, delete-orphan")
    )

    # Metadata
    provider = db.Column(db.String(40), default="internal", nullable=False)  # internal|google_meet|zoom|teams|other
    status = db.Column(db.String(20), default="scheduled", nullable=False, index=True)  # scheduled|rescheduled|canceled|completed
    scheduled_for = db.Column(db.DateTime, nullable=False, index=True)  # store in UTC
    duration_minutes = db.Column(db.Integer, nullable=True, default=30)

    # Joining / context
    join_url = db.Column(db.String(512), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    # Audit
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_by = db.relationship("User", foreign_keys=[created_by_id])

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Optional: unique UID for ICS/event references
    invite_uid = db.Column(db.String(120), nullable=True, unique=True, index=True)

    def __repr__(self):
        return f"<Meeting id={self.id} task_id={self.task_id} status={self.status} at={self.scheduled_for}>"
