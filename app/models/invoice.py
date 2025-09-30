from datetime import datetime
from ..extensions import db


class Invoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey(
        'task_request.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default="USD")
    # unpaid|paid|refunded|void
    status = db.Column(db.String(20), default="unpaid")
    issued_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime)
    gateway_ref = db.Column(db.String(120))

    task = db.relationship('TaskRequest', backref='invoices')

    # strings / nullable True is fine for MVP
    pesapal_tracking_id = db.Column(db.String(64))   # order_tracking_id
    pesapal_merchant_ref = db.Column(db.String(64))  # your unique ref you send as "id"
    gateway = db.Column(db.String(32), default='pesapal')
    gateway_status = db.Column(db.String(32))        # COMPLETED/FAILED/PENDING etc.
    gateway_meta = db.Column(db.JSON)                # raw response blobs

