# app/models/support.py
from datetime import datetime
from app.extensions import db  # make sure you have db = SQLAlchemy() in extensions.py

class SupportTicket(db.Model):
    __tablename__ = "support_ticket"
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.String(16), unique=True, index=True, nullable=False)
    # NEW
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), index=True, nullable=True)
    ip_address = db.Column(db.String(45), index=True)  # IPv4/IPv6

    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False, index=True)
    category = db.Column(db.String(64), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="open", index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    attachments = db.relationship("SupportAttachment", backref="ticket", cascade="all, delete-orphan")

class SupportMessage(db.Model):
    __tablename__ = "support_message"
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("support_ticket.id", ondelete="CASCADE"), nullable=False, index=True)
    author_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    author_role = db.Column(db.String(10), nullable=False)  # 'user' | 'admin' | 'system'
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # optional: message-scoped attachments (uses same table)
    attachments = db.relationship("SupportAttachment", backref="message", cascade="all, delete-orphan")

# allow attachment to belong to a message (optional, else remains ticket-level)
class SupportAttachment(db.Model):
    __tablename__ = "support_attachment"
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("support_ticket.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = db.Column(db.Integer, db.ForeignKey("support_message.id", ondelete="SET NULL"), nullable=True, index=True)
    filename = db.Column(db.String(255), nullable=False)
    path = db.Column(db.String(512), nullable=False)
    size_bytes = db.Column(db.Integer, nullable=False)
    mime = db.Column(db.String(100))