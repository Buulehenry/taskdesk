# app/models/feedback.py
from app.extensions import db
from datetime import datetime

class Rating(db.Model):
    __tablename__ = "ratings"

    id = db.Column(db.Integer, primary_key=True)
    # ⬇️ fix FK target
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    name = db.Column(db.String(120), nullable=True)
    email = db.Column(db.String(255), nullable=True)
    stars = db.Column(db.Integer, nullable=False)  # 1..5
    comment = db.Column(db.Text, nullable=True)
    is_public = db.Column(db.Boolean, default=True, nullable=False)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    ip = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # (optional)
    user = db.relationship("User", lazy="joined")

    __table_args__ = (
        db.Index("ix_ratings_created_at", "created_at"),
        db.Index("ix_ratings_is_deleted_public", "is_deleted", "is_public"),
    )
