# app/models/fileasset.py
from datetime import datetime
from ..extensions import db

class FileAsset(db.Model):
    __tablename__ = "file_asset"

    id = db.Column(db.Integer, primary_key=True)

    # who uploaded/owns the file (user)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)

    # optional: link the asset to a task
    task_id = db.Column(db.Integer, db.ForeignKey('task_request.id'), index=True, nullable=True)
    kind = db.Column(db.String(50), index=True) 

    # storage info
    path = db.Column(db.String(512))            # stored path on disk/cloud
    filename = db.Column(db.String(255))
    mime = db.Column(db.String(120))
    size_bytes = db.Column(db.Integer)

    # ACL / meta
    visibility = db.Column(db.String(20), default="private")
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # relationships
    owner = db.relationship("User", back_populates="file_assets")
