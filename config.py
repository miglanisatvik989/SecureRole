import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    AUDIT_INTEGRITY_KEY = os.environ.get("AUDIT_INTEGRITY_KEY")
    LOGIN_SOURCE_LIMIT = int(os.environ.get("LOGIN_SOURCE_LIMIT", "10"))
    LOGIN_ACCOUNT_LIMIT = int(os.environ.get("LOGIN_ACCOUNT_LIMIT", "5"))
    LOGIN_WINDOW_SECONDS = int(os.environ.get("LOGIN_WINDOW_SECONDS", "60"))
    SQLALCHEMY_DATABASE_URI = "sqlite:///securerole.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"hide_parameters": True}

    # Ordinary form submissions do not need large bodies or many multipart fields.
    MAX_CONTENT_LENGTH = 64 * 1024
    MAX_FORM_MEMORY_SIZE = 64 * 1024
    MAX_FORM_PARTS = 32
    TRUSTED_HOSTS = [host.strip() for host in os.environ.get("TRUSTED_HOSTS", "").split(",") if host.strip()] or None

    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_REFRESH_EACH_REQUEST = False

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE") == "1"
