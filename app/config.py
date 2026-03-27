import os
from datetime import timedelta


class Config:
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    DEFAULT_DEV_DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'payg_solar_dev.db')}"

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me-please-update")
    JWT_SECRET_KEY = os.getenv(
        "JWT_SECRET_KEY", "jwt-secret-change-me-please-use-32-characters"
    )
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or DEFAULT_DEV_DATABASE_URL
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=12)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
    MOBILE_MONEY_MODE = os.getenv("MOBILE_MONEY_MODE", "mock")
    MTN_MOMO_BASE_URL = os.getenv("MTN_MOMO_BASE_URL", "")
    MTN_MOMO_API_KEY = os.getenv("MTN_MOMO_API_KEY", "")
    ORANGE_MONEY_BASE_URL = os.getenv("ORANGE_MONEY_BASE_URL", "")
    ORANGE_MONEY_CLIENT_ID = os.getenv("ORANGE_MONEY_CLIENT_ID", "")
    ORANGE_MONEY_CLIENT_SECRET = os.getenv("ORANGE_MONEY_CLIENT_SECRET", "")
    DEVICE_SHARED_SECRET = os.getenv("DEVICE_SHARED_SECRET", "device-secret")
    PAYMENT_WEBHOOK_SECRET = os.getenv("PAYMENT_WEBHOOK_SECRET", DEVICE_SHARED_SECRET)
    IOT_ALLOW_LEGACY_DEVICE_SECRET = os.getenv(
        "IOT_ALLOW_LEGACY_DEVICE_SECRET", "true"
    ).lower() == "true"
    IOT_SIGNATURE_MAX_SKEW_SECONDS = int(os.getenv("IOT_SIGNATURE_MAX_SKEW_SECONDS", "300"))
    IOT_NONCE_TTL_SECONDS = int(os.getenv("IOT_NONCE_TTL_SECONDS", "86400"))
    SCHEDULER_ENABLED = os.getenv("SCHEDULER_ENABLED", "true").lower() == "true"
    ENABLE_SECURITY_HEADERS = os.getenv("ENABLE_SECURITY_HEADERS", "true").lower() == "true"
    ENABLE_HSTS = os.getenv("ENABLE_HSTS", "false").lower() == "true"
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH_MB", "2")) * 1024 * 1024
    TRUST_PROXY_COUNT = int(os.getenv("TRUST_PROXY_COUNT", "0"))
    RATELIMIT_ENABLED = os.getenv("RATELIMIT_ENABLED", "true").lower() == "true"
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_DEFAULT = os.getenv("RATELIMIT_DEFAULT", "300 per minute")
    RATELIMIT_AUTH_LOGIN = os.getenv("RATELIMIT_AUTH_LOGIN", "10 per minute")
    RATELIMIT_AUTH_REGISTER = os.getenv("RATELIMIT_AUTH_REGISTER", "5 per minute")
    RATELIMIT_PAYMENT_WEBHOOK = os.getenv("RATELIMIT_PAYMENT_WEBHOOK", "60 per minute")
    RATELIMIT_IOT_INGEST = os.getenv("RATELIMIT_IOT_INGEST", "120 per minute")


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///test_payg.db"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=30)
    RATELIMIT_ENABLED = False


class ProductionConfig(Config):
    DEBUG = False
    SCHEDULER_ENABLED = os.getenv("SCHEDULER_ENABLED", "false").lower() == "true"
    IOT_ALLOW_LEGACY_DEVICE_SECRET = os.getenv(
        "IOT_ALLOW_LEGACY_DEVICE_SECRET", "false"
    ).lower() == "true"


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
