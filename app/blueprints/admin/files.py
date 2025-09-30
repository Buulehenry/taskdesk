from io import BytesIO
import os
from PIL import Image
from flask import send_file
from flask_login import login_required
from ...security import roles_required
from ...extensions import db  # not used, but fine to keep pattern
from ...models.fileasset import FileAsset
from . import admin_bp
from .utils import _load_asset_stream, _THUMBS_ROOT, _etag

@admin_bp.get('/secure/file/<int:file_id>')
@login_required
@roles_required('admin')
def secure_file(file_id):
    fa = FileAsset.query.get_or_404(file_id)
    stream, mime, filename = _load_asset_stream(fa)
    data = stream.getvalue()
    etag = _etag(data)

    inline_types = ("image/", "text/", "audio/", "video/", "application/pdf")
    as_attachment = not mime.startswith(inline_types)

    resp = send_file(
        BytesIO(data),
        mimetype=mime,
        as_attachment=as_attachment,
        download_name=filename,
        conditional=True,
        max_age=3600,
    )
    resp.set_etag(etag)
    resp.headers["Cache-Control"] = "private, max-age=3600"
    return resp

@admin_bp.get('/secure/thumb/<int:file_id>')
@login_required
@roles_required('admin')
def secure_thumb(file_id):
    fa = FileAsset.query.get_or_404(file_id)
    stream, mime, filename = _load_asset_stream(fa)

    if not mime.startswith("image/"):
        return secure_file(file_id)

    os.makedirs(_THUMBS_ROOT(), exist_ok=True)
    name_no_ext, _ = os.path.splitext(filename)
    thumb_path = os.path.join(_THUMBS_ROOT(), f"{fa.id}_320.jpg")

    if not os.path.exists(thumb_path):
        img = Image.open(stream)
        img.thumbnail((320, 320))
        img = img.convert("RGB")
        img.save(thumb_path, "JPEG", quality=82, optimize=True)

    with open(thumb_path, "rb") as f:
        data = f.read()

    resp = send_file(
        BytesIO(data),
        mimetype="image/jpeg",
        as_attachment=False,
        download_name=f"{name_no_ext}_thumb.jpg",
        conditional=True,
        max_age=43200,
    )
    resp.headers["Cache-Control"] = "private, max-age=43200"
    return resp
