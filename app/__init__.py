import os
import json
from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from flask import Flask, render_template, request, session, g  # + request, session
from .extensions import db, migrate, login_manager, csrf, mail, babel  # + babel
from .config import Config
from .models.user import User
from flask_login import current_user  # for locale selector
from flask_babel import get_locale
from sqlalchemy import func
from app.models.feedback import Rating

# Blueprints
from .blueprints.errors import errors_bp
from .blueprints.auth.routes import auth_bp
from .blueprints.client.routes import client_bp
from .blueprints.admin import admin_bp
from .blueprints.freelancer.routes import freelancer_bp
from .blueprints.payments.routes import payments_bp
from .blueprints.main import main_bp
from .blueprints.pesapal_ipn import pesapal_ipn_bp


# Optional: Sentry
def _init_sentry(app):
    dsn = app.config.get("SENTRY_DSN")
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=dsn,
            integrations=[FlaskIntegration(), SqlalchemyIntegration()],
            traces_sample_rate=app.config.get("SENTRY_TRACES_SAMPLE_RATE", 0.0),
            environment=os.getenv("ENV", "development"),
            release=os.getenv("GIT_COMMIT", None),
            send_default_pii=False,
        )
        app.logger.info("Sentry initialized.")
    except Exception as e:
        app.logger.warning(f"Sentry init failed: {e}")

def _init_logging(app):
    # Base level
    level_name = app.config.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    app.logger.setLevel(level)

    # Ensure log dir exists
    log_dir = Path(app.config.get("LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / app.config.get("LOG_FILENAME", "taskdesk.log")
    Path(app.instance_path, "resumes").mkdir(parents=True, exist_ok=True)


    # Formatter: text or JSON
    if app.config.get("LOG_JSON", False):
        try:
            import json_log_formatter
            formatter = json_log_formatter.JSONFormatter()
        except Exception:
            formatter = logging.Formatter("[%(asctime)s] %(levelname)s in %(module)s: %(message)s")
    else:
        formatter = logging.Formatter("[%(asctime)s] %(levelname)s in %(module)s: %(message)s")

    # Rotating file handler (5MB x 5)
    file_handler = RotatingFileHandler(
        log_path, maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    app.logger.addHandler(file_handler)

    # Stream to stdout as well (useful on dev/heroku/docker)
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter)
    app.logger.addHandler(stream_handler)

    app.logger.info("Logging initialized.")

def create_app(config_object=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object)

    if config_object is None:
        app.config.from_object(Config)
    else:
        app.config.from_object(config_object)
        
    # --- base config defaults (your existing defaults kept as-is) ---
    app.config.setdefault("SECRET_KEY", "change-me")
    app.config.setdefault(
        "SQLALCHEMY_DATABASE_URI",
        "sqlite:///" + os.path.join(app.instance_path, "taskdesk.db"),
    )
    app.config.setdefault("SQLALCHEMY_TRACK_MODIFICATIONS", False)

    # i18n defaults (Babel)
    app.config.setdefault("BABEL_DEFAULT_LOCALE", "en")
    app.config.setdefault("BABEL_DEFAULT_TIMEZONE", "UTC")
    app.config.setdefault("LANGUAGES", ["en", "fr", "de", "sw"])

    # ensure instance & uploads
    from pathlib import Path as _Path
    _Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    default_upload_dir = _Path(app.instance_path) / "uploads"
    app.config.setdefault("UPLOAD_FOLDER", str(default_upload_dir))
    app.config.setdefault("MAX_CONTENT_LENGTH", 50 * 1024 * 1024)
    app.config.setdefault("ALLOWED_EXTENSIONS", {"pdf","doc","docx","xls","xlsx","ppt","pptx","txt","zip","png","jpg","jpeg"})
    default_upload_dir.mkdir(parents=True, exist_ok=True)

    # Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    mail.init_app(app)

    # ---- Babel init (locale from session/user/Accept-Language) ----
    def _select_locale():
        return (
            session.get("lang")
            or (getattr(current_user, "language", None) if getattr(current_user, "is_authenticated", False) else None)
            or request.accept_languages.best_match(app.config.get("LANGUAGES", ["en"]))
            or "en"
        )
    babel.init_app(app, locale_selector=_select_locale)
    # ---------------------------------------------------------------

    @app.context_processor
    def inject_i18n_helpers():
        def _safe_get_locale():
            # get_locale() can return None early in the request
            loc = get_locale()
            return str(loc) if loc else "en"
        return {"get_locale": _safe_get_locale}

    app.config.from_pyfile("config.py", silent=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    login_manager.login_view = "auth.login"

    @app.context_processor
    def inject_now():
        return {"now": datetime.utcnow}
    
    from time import time
    _ratings_cache = {"t": 0, "avg": 0.0, "cnt": 0}

    @app.context_processor
    def inject_ratings_aggregate():
        now = time()
        if now - _ratings_cache["t"] > 60:
            avg, cnt = db.session.query(
                func.coalesce(func.avg(Rating.stars), 0.0),
                func.count(Rating.id)
            ).filter(Rating.is_deleted.is_(False), Rating.is_public.is_(True)).one()
            _ratings_cache.update({"t": now, "avg": round(float(avg or 0.0), 1), "cnt": int(cnt or 0)})
        return {"rating_avg": _ratings_cache["avg"], "rating_count": _ratings_cache["cnt"]}
    
    @app.before_request
    def _load_cookie_consent():
        raw = request.cookies.get("td.consent")
        default = {"essential": True, "analytics": False, "marketing": False, "ts": None}
        try:
            g.cookie_consent = {**default, **(json.loads(raw) if raw else {})}
        except Exception:
            g.cookie_consent = default

    @app.context_processor
    def inject_cookie_consent():
        return {
            "cookie_consent": getattr(g, "cookie_consent", {"essential": True}),
            "should_show_cookie_banner": not request.cookies.get("td.consent"),
        }
    # Logging must come before blueprints so errors during register are captured
    _init_logging(app)
    _init_sentry(app)

    # Blueprints
    app.register_blueprint(errors_bp)  # error handlers
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(client_bp, url_prefix="/client")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(freelancer_bp, url_prefix="/freelancer")
    app.register_blueprint(payments_bp, url_prefix="/payments")
    app.register_blueprint(pesapal_ipn_bp)

    # Simple index
    @app.route("/")
    def index():
        from flask_login import current_user
        return render_template("home.html")
    
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(error):
        return render_template("errors/500.html"), 500

    @app.errorhandler(401)
    def unauthorized_error(error):
        return render_template("errors/401.html"), 401

    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template("errors/403.html"), 403

    return app
