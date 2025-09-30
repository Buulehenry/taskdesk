# app/services/storage_service.py
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import current_app

def _ensure_base() -> Path:
    # Fallback to <instance>/uploads if UPLOAD_FOLDER not configured yet
    base = current_app.config.get("UPLOAD_FOLDER")
    if not base:
        base = Path(current_app.instance_path) / "uploads"
    else:
        base = Path(base)
    base.mkdir(parents=True, exist_ok=True)
    return base

def allowed_ext(filename: str) -> bool:
    exts = current_app.config.get("ALLOWED_EXTENSIONS")
    if not exts:
        exts = {"pdf","doc","docx","xls","xlsx","ppt","pptx","txt","zip","png","jpg","jpeg"}
    suffix = Path(filename).suffix.lower().lstrip(".")
    return bool(suffix) and suffix in exts

def save_upload(file_storage, subdir: str = "") -> str:
    """
    Saves file to UPLOAD_FOLDER / subdir / <safe_name>, returns relative path from base.
    """
    base = _ensure_base()
    safe_name = secure_filename(file_storage.filename or "")
    if not safe_name:
        raise ValueError("Empty filename")

    target_dir = base / subdir if subdir else base
    target_dir.mkdir(parents=True, exist_ok=True)

    dest = target_dir / safe_name
    file_storage.save(dest)

    # Return path relative to base for storage in DB
    return str(dest.relative_to(base))
