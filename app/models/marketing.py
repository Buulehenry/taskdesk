# app/models/marketing.py
from datetime import datetime
import uuid
from app.extensions import db

def _tok() -> str:
    return uuid.uuid4().hex

class Subscriber(db.Model):
    __tablename__ = "subscriber"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120))
    source = db.Column(db.String(50))                   # e.g., 'footer', 'landing', 'admin'
    token = db.Column(db.String(64), unique=True, default=_tok, nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)  # false if unsubscribed
    verified_at = db.Column(db.DateTime)               # set if you later add double opt-in
    unsubscribed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class EmailCampaign(db.Model):
    __tablename__ = "email_campaign"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)   # internal name
    subject = db.Column(db.String(200), nullable=False)
    body_text = db.Column(db.Text, nullable=True)
    body_html = db.Column(db.Text, nullable=True)
    segment = db.Column(db.String(20), default="subscribers", nullable=False)  # 'subscribers'|'users'|'both'
    created_by = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    sent_at = db.Column(db.DateTime)
