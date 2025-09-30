# app/models/user.py
from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from ..extensions import db


# ------- Core Models -------

class User(UserMixin, db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(50))

    password_hash = db.Column(db.String(255))

    # client|admin|freelancer
    role = db.Column(db.String(20), nullable=False, default="client", index=True)
    is_staff = db.Column(db.Boolean, default=False)

    # active|suspended|pending
    status = db.Column(db.String(20), default="active", index=True)

    # Extra account signals
    is_email_verified = db.Column(db.Boolean, default=False)
    mfa_enabled = db.Column(db.Boolean, default=False)
    last_login_at = db.Column(db.DateTime)
    deleted_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Profiles (one-to-one)
    client_profile = db.relationship(
        "ClientProfile",
        backref="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    freelancer_profile = db.relationship(
        "FreelancerProfile",
        backref="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    # Assets / Experience / Education
    file_assets = db.relationship(
        "FileAsset",
        back_populates="owner",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    experiences = db.relationship(
        "FreelancerExperience",
        backref="user",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    educations = db.relationship(
        "FreelancerEducation",
        backref="user",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    # --- KYC relationships (DISAMBIGUATED) ---
    # A user's own KYC submissions (they are the subject)
    kyc_submissions = db.relationship(
        "KycSubmission",
        foreign_keys="KycSubmission.user_id",
        backref="subject",  # in KycSubmission: .subject -> User (freelancer)
        lazy="dynamic",
        order_by="KycSubmission.submitted_at.desc()",
        cascade="all, delete-orphan",
    )
    # KYC reviews performed by this user (as an admin)
    kyc_reviews = db.relationship(
        "KycSubmission",
        foreign_keys="KycSubmission.reviewed_by",
        backref="reviewer_user",  # in KycSubmission: .reviewer_user -> User (admin)
        lazy="dynamic",
    )

    # --- Auth helpers ---
    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    # --- Convenience flags ---
    @property
    def is_active_account(self) -> bool:
        return self.status == "active" and self.deleted_at is None

    @property
    def is_suspended(self) -> bool:
        return self.status == "suspended"
    
    @property
    def kyc_status(self):
        fp = self.freelancer_profile
        return fp.kyc_status if fp else None

    def mark_login(self):
        self.last_login_at = datetime.utcnow()

    # Used to decide if freelancer can accept assignments
    def can_accept_assignments(self) -> bool:
        if self.role != "freelancer":
            return False
        if not self.is_active_account:
            return False
        fp = self.freelancer_profile
        if not fp:
            return False
        # Allow acceptance if KYC approved OR relax for MVP
        return fp.kyc_status in ("approved",) or True


class ClientProfile(db.Model):
    __tablename__ = "client_profile"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, index=True)
    company = db.Column(db.String(255))
    billing_email = db.Column(db.String(255))
    default_currency = db.Column(db.String(10), default="USD")


class FreelancerProfile(db.Model):
    __tablename__ = "freelancer_profile"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, index=True)

    # Public/profile info used in matching
    headline = db.Column(db.String(160))
    bio = db.Column(db.Text)
    skills = db.Column(db.Text)                 # CSV or JSON for MVP
    location = db.Column(db.String(120))
    portfolio_url = db.Column(db.String(255))
    payout_email = db.Column(db.String(255))

    nda_signed_at = db.Column(db.DateTime)

    # Vetting/approval from admins: pending|approved|rejected
    approval_status = db.Column(db.String(20), default="pending", index=True)

    # KYC surface for quick read; detailed records live in KycSubmission
    # unverified|submitted|approved|rejected
    kyc_status = db.Column(db.String(20), default="unverified", index=True)
    kyc_checked_at = db.Column(db.DateTime)

    # Quality metrics
    rating_avg = db.Column(db.Float, default=0.0)
    completed_tasks = db.Column(db.Integer, default=0)



# ------- Experience & Education -------

class FreelancerExperience(db.Model):
    __tablename__ = "freelancer_experience"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)

    title = db.Column(db.String(160), nullable=False)
    company = db.Column(db.String(160))
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)  # None = present
    summary = db.Column(db.Text)
    skills = db.Column(db.String(512))  # tags relevant to this role

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FreelancerEducation(db.Model):
    __tablename__ = "freelancer_education"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)

    school = db.Column(db.String(160))
    degree = db.Column(db.String(160))
    field = db.Column(db.String(160))
    start_year = db.Column(db.Integer)
    end_year = db.Column(db.Integer)
    notes = db.Column(db.Text)


# ------- KYC -------

class KycSubmission(db.Model):
    __tablename__ = "kyc_submission"

    id = db.Column(db.Integer, primary_key=True)

    # The freelancer being verified
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    # The admin who reviewed (optional until review happens)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('user.id'))

    doc_type = db.Column(db.String(50))
    id_number = db.Column(db.String(120))
    country = db.Column(db.String(120))

    file_id_front  = db.Column(db.Integer, db.ForeignKey('file_asset.id'))
    file_id_back   = db.Column(db.Integer, db.ForeignKey('file_asset.id'))
    file_id_selfie = db.Column(db.Integer, db.ForeignKey('file_asset.id'))

    status = db.Column(db.String(20), default='submitted')  # submitted|approved|rejected
    review_note = db.Column(db.Text)

    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at  = db.Column(db.DateTime)

    # NOTE: relationships to User are provided via User.kyc_submissions / User.kyc_reviews.
    # This avoids ambiguous-FK mapper errors.

    # Links to uploaded files (FileAsset)
    front_asset  = db.relationship('FileAsset', foreign_keys=[file_id_front])
    back_asset   = db.relationship('FileAsset', foreign_keys=[file_id_back])
    selfie_asset = db.relationship('FileAsset', foreign_keys=[file_id_selfie])

