import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Application configuration settings."""

    # Google OAuth
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "default-client-id")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "default-client-secret")
    GOOGLE_REDIRECT_URI = "https://magnet-custom.onrender.com/auth/callback/google"
    GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"

    # Email settings
    SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret-key")
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))  # safer conversion
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "True").lower() in ("true", "1")
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = (
        os.getenv("MAIL_DEFAULT_SENDER") or MAIL_USERNAME or "no-reply@example.com"
    )

    # Database settings
    SQLALCHEMY_DATABASE_URI = os.getenv("EXTERNAL_DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 5,
        'max_overflow': 10,
        'pool_timeout': 30,
        'pool_recycle': 1800,
    }


    # JWT Authentication
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "fallback-jwt-secret")

    # SQLAlchemy Session Configuration
    SESSION_TYPE = "sqlalchemy"
    SESSION_SQLALCHEMY_TABLE = 'sessions'
    SESSION_PERMANENT = True
    SESSION_USE_SIGNER = True
    SESSION_KEY_PREFIX = "session:"
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 86400  # 24 hours

    # Frontend URL fallback
    FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173')
