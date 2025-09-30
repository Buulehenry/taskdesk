from datetime import datetime
from ..extensions import db

class Quote(db.Model):
    __tablename__ = 'quote'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('task_request.id'), nullable=False, index=True)

    proposed_price = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default='UGX')
    status = db.Column(db.String(20), default='pending', index=True)  # pending|accepted|declined
    pay_option = db.Column(db.String(20), default='pay_on_delivery')   # pay_now|pay_on_delivery
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # models/quote.py  (fields to add)
    client_counter_amount   = db.Column(db.Numeric(12,2))
    client_counter_currency = db.Column(db.String(10))  # default to quote.currency
    client_counter_reason   = db.Column(db.Text)
    client_counter_status   = db.Column(db.String(20), index=True)  # None|pending|accepted|rejected
    client_counter_at       = db.Column(db.DateTime)

    # NEW:
    valid_until = db.Column(db.DateTime, nullable=True, index=True)

    task = db.relationship('TaskRequest', back_populates='quotes')
