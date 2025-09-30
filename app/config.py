# app/config.py
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def _as_bool(val: str | None, default=False) -> bool:
    if val is None:
        return default
    return str(val).strip().lower() in {"1", "true", "yes", "on"}

class Config:
    # --- Core ---
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    APP_VERSION = os.getenv("APP_VERSION")
    EXTERNAL_BASE_URL = os.getenv("EXTERNAL_BASE_URL")
    BABEL_DEFAULT_LOCALE = os.getenv("BABEL_DEFAULT_LOCALE")
    BABEL_DEFAULT_TIMEZONE = os.getenv("BABEL_DEFAULT_TIMEZONE")
    RATING_THROTTLE_SECONDS = os.getenv("RATING_THROTTLE_SECONDS")

    # DB
    SQLALCHEMY_DATABASE_URI = (
        os.getenv("SQLALCHEMY_DATABASE_URI")
        or os.getenv("DATABASE_URL")
        or "sqlite:///dfy.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # CSRF
    WTF_CSRF_TIME_LIMIT = None

    # --- Uploads ---
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "instance/uploads")
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(50 * 1024 * 1024)))  # 50MB

    # --- Mail ---
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USE_TLS = _as_bool(os.getenv("MAIL_USE_TLS", "1"))
    MAIL_USE_SSL = _as_bool(os.getenv("MAIL_USE_SSL", "0"))  # don't enable together with TLS
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", MAIL_USERNAME)
    MAIL_SUPPRESS_SEND = _as_bool(os.getenv("MAIL_SUPPRESS_SEND", "0"))
    MAIL_MAX_EMAILS = None
    MAIL_ASCII_ATTACHMENTS = False

    # --- Logging ---
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR = os.getenv("LOG_DIR", "logs")
    LOG_FILENAME = os.getenv("LOG_FILENAME", "taskdesk.log")
    LOG_JSON = _as_bool(os.getenv("LOG_JSON", "0"))

    # --- Sentry ---
    SENTRY_DSN = os.getenv("SENTRY_DSN", "")
    SENTRY_TRACES_SAMPLE_RATE = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0"))

    # --- URL building for emails (absolute links) ---
    # Set these via .env. In dev you can omit SERVER_NAME so Flask derives from the request.
    SERVER_NAME = os.getenv("SERVER_NAME")  # e.g. "app.yourdomain.com"
    PREFERRED_URL_SCHEME = os.getenv("PREFERRED_URL_SCHEME", "https")

    # --- Payments: Pesapal ---
    PESAPAL_CONSUMER_KEY = os.getenv("PESAPAL_CONSUMER_KEY")
    PESAPAL_CONSUMER_SECRET = os.getenv("PESAPAL_CONSUMER_SECRET")
    PESAPAL_USE_SANDBOX = _as_bool(os.getenv("PESAPAL_USE_SANDBOX"))  # True in dev
    PESAPAL_IPN_ID = os.getenv("PESAPAL_IPN_ID")  # GUID returned when registering IPN
    PESAPAL_CALLBACK_URL = os.getenv("PESAPAL_CALLBACK_URL")  # e.g. "https://your-domain.com/payments/return"
    PESAPAL_CANCELLATION_URL = os.getenv("PESAPAL_CANCELLATION_URL")  # can reuse callback

    # --- Security cookies (recommended for prod) ---
    SESSION_COOKIE_SECURE = _as_bool(os.getenv("SESSION_COOKIE_SECURE", "1"))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
