from flask import render_template, request
from werkzeug.exceptions import HTTPException
from flask_wtf.csrf import CSRFError
from ...extensions import db
from . import errors_bp

# 401 – Unauthorized
@errors_bp.app_errorhandler(401)
def err_401(e):
    return render_template("errors/401.html", error=e), 401

# 403 – Forbidden
@errors_bp.app_errorhandler(403)
def err_403(e):
    return render_template("errors/403.html", error=e), 403

# 404 – Not Found
@errors_bp.app_errorhandler(404)
def err_404(e):
    return render_template("errors/404.html", path=request.path), 404

# 405 – Method Not Allowed
@errors_bp.app_errorhandler(405)
def err_405(e):
    return render_template("errors/405.html", error=e), 405

# 413 – Payload Too Large (useful for uploads)
@errors_bp.app_errorhandler(413)
def err_413(e):
    return render_template("errors/413.html", error=e), 413

# 429 – Too Many Requests (if you ever add rate limiting)
@errors_bp.app_errorhandler(429)
def err_429(e):
    return render_template("errors/429.html", error=e), 429

# CSRF – typically treated as 400 Bad Request
@errors_bp.app_errorhandler(CSRFError)
def err_csrf(e):
    # e.description is human-readable
    return render_template("errors/400_csrf.html", error=e), 400

# 500 – Internal Server Error
@errors_bp.app_errorhandler(500)
def err_500(e):
    # if a DB action caused this, rollback so app isn’t stuck in bad transaction
    try:
        db.session.rollback()
    except Exception:
        pass
    return render_template("errors/500.html"), 500

# Fallback for uncaught HTTPException (shows friendly page with code/desc)
@errors_bp.app_errorhandler(HTTPException)
def err_http(e: HTTPException):
    # If not specifically handled above, render a generic HTTP error page.
    return render_template("errors/http_generic.html", code=e.code, name=e.name, description=e.description), e.code

# Last-resort: any other Exception
@errors_bp.app_errorhandler(Exception)
def err_unexpected(e):
    try:
        db.session.rollback()
    except Exception:
        pass
    # Don’t leak internals—just show generic 500
    return render_template("errors/500.html"), 500
