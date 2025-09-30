from app.extensions import db
from datetime import datetime

class JobPosting(db.Model):
    __tablename__ = "job_postings"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    location = db.Column(db.String(120), nullable=True)            # e.g. "Nairobi · Hybrid"
    department = db.Column(db.String(120), nullable=True)
    employment_type = db.Column(db.String(80), nullable=True)       # Full-time, Contract…
    description_md = db.Column(db.Text, nullable=False)             # Markdown/HTML
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class JobApplication(db.Model):
    __tablename__ = "job_applications"
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("job_postings.id"), nullable=False)
    job = db.relationship("JobPosting", backref=db.backref("applications", lazy="dynamic"))
    name = db.Column(db.String(160), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(80), nullable=True)
    cover_letter = db.Column(db.Text, nullable=True)
    resume_path = db.Column(db.String(500), nullable=True)
    resume_filename = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
