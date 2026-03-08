import os
from datetime import timedelta


def _jwt_expiration_from_env(default_days: int, minutes_env: str, days_env: str, min_days: int | None = None) -> timedelta:
    """Pick JWT expiry from env; prefer days, then minutes, else default, with an optional floor."""
    if os.environ.get(days_env):
        exp = timedelta(days=int(os.environ[days_env]))
    elif os.environ.get(minutes_env):
        exp = timedelta(minutes=int(os.environ[minutes_env]))
    else:
        exp = timedelta(days=default_days)

    if min_days is not None:
        # Enforce a minimum lifetime so logins stay valid for the desired window.
        exp = max(exp, timedelta(days=min_days))

    return exp

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class BaseConfig:
    USE_REDIS = os.environ.get("USE_REDIS", "true").lower() == "true"
    USE_CELERY = os.environ.get("USE_CELERY", "true").lower() == "true"
    USE_DOCKER_SERVICES = os.environ.get("USE_DOCKER_SERVICES", "true").lower() == "true"
    USE_AWS = os.environ.get("USE_AWS", "true").lower() == "true"
    USE_ELASTICSEARCH = os.environ.get("USE_ELASTICSEARCH", "true").lower() == "true"
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'social.db')}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "true").lower() == "true"
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    REMEMBER_COOKIE_HTTPONLY = True
    WTF_CSRF_ENABLED = True
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "jwt-secret")
    JWT_TOKEN_LOCATION = ["headers", "cookies"]
    # Make JWT cookies persistent; honor token exp instead of closing with the browser.
    JWT_SESSION_COOKIE = False
    JWT_COOKIE_SECURE = SESSION_COOKIE_SECURE
    JWT_COOKIE_SAMESITE = "Lax"
    JWT_ACCESS_TOKEN_EXPIRES = _jwt_expiration_from_env(365, "JWT_ACCESS_MINUTES", "JWT_ACCESS_DAYS", min_days=365)
    JWT_REFRESH_TOKEN_EXPIRES = _jwt_expiration_from_env(365, "JWT_REFRESH_MINUTES", "JWT_REFRESH_DAYS", min_days=365)
    JWT_COOKIE_CSRF_PROTECT = True
    RATELIMIT_HEADERS_ENABLED = True
    REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    SECURITY_PASSWORD_SALT = os.environ.get("SECURITY_PASSWORD_SALT", "change-salt")
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USERNAME = "multimosaic.help@gmail.com"
    MAIL_PASSWORD = "hznr lmmn wdve zcjy"
    MAIL_DEFAULT_SENDER = "multimosaic.help@gmail.com"
    FCM_SERVER_KEY = os.environ.get("FCM_SERVER_KEY")
    FCM_API_URL = os.environ.get("FCM_API_URL", "https://fcm.googleapis.com/fcm/send")
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
    GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "https://aurora-ind.onrender.com/google/callback")
    AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
    AWS_S3_BUCKET = os.environ.get("AWS_S3_BUCKET", "local-bucket")
    AWS_S3_REGION = os.environ.get("AWS_S3_REGION", "us-east-1")
    LOCAL_STORAGE_PATH = os.environ.get("LOCAL_STORAGE_PATH", "local_uploads")
    LOCAL_STORAGE_BASE_URL = os.environ.get("LOCAL_STORAGE_BASE_URL", "/static/uploads")
    AWS_S3_SIGNED_TTL = int(os.environ.get("AWS_S3_SIGNED_TTL", 3600))
    AWS_REPLAY_PREFIX = os.environ.get("AWS_REPLAY_PREFIX", "replays/")
    MAX_CONTENT_LENGTH = 64 * 1024 * 1024  # allow rich media uploads
    LOG_DIR = os.environ.get("LOG_DIR", "logs")
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    SECURITY_LOG_PATH = os.path.join(LOG_DIR, "security.log")
    APP_LOG_PATH = os.path.join(LOG_DIR, "app.log")
    AUDIT_LOG_PATH = os.path.join(LOG_DIR, "audit.log")
    METRICS_LOG_PATH = os.path.join(LOG_DIR, "metrics.log")
    ADMIN_PAGE_SIZE = int(os.environ.get("ADMIN_PAGE_SIZE", 50))
    HSTS_ENABLED = os.environ.get("HSTS_ENABLED", "true").lower() == "true"
    HSTS_MAX_AGE = int(os.environ.get("HSTS_MAX_AGE", 31536000))
    CSP_ADDITIONAL_SOURCES = os.environ.get(
        "CSP_ADDITIONAL_SOURCES",
        "https://cdn.jsdelivr.net,https://cdnjs.cloudflare.com,https://tenor.googleapis.com,https://g.tenor.com,https://media.tenor.com,https://media1.tenor.com,https://media2.tenor.com,https://media3.tenor.com",
    )
    RATE_LIMIT_DEFAULT = os.environ.get("RATE_LIMIT_DEFAULT", "200 per day;50 per hour")
    RATE_LIMIT_ADMIN = os.environ.get("RATE_LIMIT_ADMIN", "200 per hour")
    RATE_LIMIT_AUTH = os.environ.get("RATE_LIMIT_AUTH", "20 per minute")
    DOWNLOAD_URL_TTL = int(os.environ.get("DOWNLOAD_URL_TTL", 3600))
    DATA_EXPORT_TTL_HOURS = int(os.environ.get("DATA_EXPORT_TTL_HOURS", 24))
    DATA_EXPORT_BUCKET = os.environ.get("DATA_EXPORT_BUCKET", "user-exports")
    THEME_DEFAULT = os.environ.get("THEME_DEFAULT", "light")
    AGE_MINIMUM = int(os.environ.get("AGE_MINIMUM", 13))
    PARENTAL_SCREEN_TIME_LIMIT_DEFAULT = int(os.environ.get("PARENTAL_SCREEN_TIME_LIMIT_DEFAULT", 180))
    MAX_FAILED_LOGINS = int(os.environ.get("MAX_FAILED_LOGINS", 5))
    CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", os.environ.get("REDIS_URL", "redis://redis:6379/0"))
    CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
    CELERY_TASK_DEFAULT_QUEUE = os.environ.get("CELERY_DEFAULT_QUEUE", "default")
    CELERY_TASK_SERIALIZER = "json"
    CELERY_ACCEPT_CONTENT = ["json"]
    CELERY_RESULT_SERIALIZER = "json"
    CELERY_TASK_TIME_LIMIT = int(os.environ.get("CELERY_TASK_TIME_LIMIT", 600))
    CELERY_BEAT_SCHEDULE = {}
    FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "ffmpeg")
    FFPROBE_BIN = os.environ.get("FFPROBE_BIN", "ffprobe")
    REEL_MAX_DURATION_SEC = int(os.environ.get("REEL_MAX_DURATION_SEC", 90))
    REEL_MAX_SIZE_MB = int(os.environ.get("REEL_MAX_SIZE_MB", 150))
    REEL_ALLOWED_MIME = {"video/mp4"}
    REEL_MAX_SCHEDULE_DAYS = int(os.environ.get("REEL_MAX_SCHEDULE_DAYS", 30))
    REEL_MAX_TEXT_OVERLAYS = int(os.environ.get("REEL_MAX_TEXT_OVERLAYS", 20))
    STORY_MAX_DURATION_SEC = int(os.environ.get("STORY_MAX_DURATION_SEC", 30))
    STORY_MAX_SIZE_MB = int(os.environ.get("STORY_MAX_SIZE_MB", 50))
    STORY_UPLOAD_LIMIT_PER_HOUR = int(os.environ.get("STORY_UPLOAD_LIMIT_PER_HOUR", 20))
    TRENDING_CACHE_TTL = int(os.environ.get("TRENDING_CACHE_TTL", 300))
    EXPLORE_CACHE_TTL = int(os.environ.get("EXPLORE_CACHE_TTL", 300))
    SEARCH_RATE_LIMIT = os.environ.get("SEARCH_RATE_LIMIT", "60 per minute")
    ELASTICSEARCH_URL = os.environ.get("ELASTICSEARCH_URL", "http://elasticsearch:9200")
    ELASTICSEARCH_USERNAME = os.environ.get("ELASTICSEARCH_USERNAME")
    ELASTICSEARCH_PASSWORD = os.environ.get("ELASTICSEARCH_PASSWORD")
    SEARCH_INDEX_PREFIX = os.environ.get("SEARCH_INDEX_PREFIX", "aurora")
    SEARCH_AUTOCOMPLETE_SIZE = int(os.environ.get("SEARCH_AUTOCOMPLETE_SIZE", 8))
    SEARCH_PAGE_SIZE = int(os.environ.get("SEARCH_PAGE_SIZE", 20))
    MODERATION_API_URL = os.environ.get("MODERATION_API_URL", "https://moderation.example.com/analyze")
    MODERATION_API_KEY = os.environ.get("MODERATION_API_KEY")
    MODERATION_AUTO_HIDE = os.environ.get("MODERATION_AUTO_HIDE", "true").lower() == "true"
    AI_CONTENT_API_URL = os.environ.get("AI_CONTENT_API_URL", "https://ai.example.com/caption")
    AI_CONTENT_API_KEY = os.environ.get("AI_CONTENT_API_KEY")
    AI_CONTENT_CACHE_TTL = int(os.environ.get("AI_CONTENT_CACHE_TTL", 86400))
    AI_RATE_LIMIT = os.environ.get("AI_RATE_LIMIT", "20 per hour")
    CATEGORY_LIST = os.environ.get("CATEGORY_LIST", "Artist,Blogger,Tech,Fitness,Travel,Food,Music,Education,Fashion,Gaming").split(",")
    RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID")
    RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET")
    RAZORPAY_WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET")
    PLATFORM_COMMISSION_RATE = float(os.environ.get("PLATFORM_COMMISSION_RATE", 0.1))
    MIN_PAYOUT_AMOUNT = int(os.environ.get("MIN_PAYOUT_AMOUNT", 5000))
    BOOST_CAMPAIGN_RATE_LIMIT = os.environ.get("BOOST_CAMPAIGN_RATE_LIMIT", "10 per day")
    BADGE_PLATFORM_FEE = float(os.environ.get("BADGE_PLATFORM_FEE", 0.1))
    ADS_PLATFORM_FEE = float(os.environ.get("ADS_PLATFORM_FEE", 0.2))
    SUBSCRIPTION_PLATFORM_FEE = float(os.environ.get("SUBSCRIPTION_PLATFORM_FEE", 0.15))
    CREATOR_CASHOUT_TTL_DAYS = int(os.environ.get("CREATOR_CASHOUT_TTL_DAYS", 7))
    LIVE_SLOW_MODE_SECONDS = int(os.environ.get("LIVE_SLOW_MODE_SECONDS", 5))
    LIVE_MAX_GUESTS = int(os.environ.get("LIVE_MAX_GUESTS", 3))
    ANALYTICS_CACHE_TTL = int(os.environ.get("ANALYTICS_CACHE_TTL", 900))


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    RATELIMIT_ENABLED = False  # Disable rate limits in local development
    USE_REDIS = os.environ.get("USE_REDIS", "false").lower() == "true"
    USE_CELERY = os.environ.get("USE_CELERY", "false").lower() == "true"
    USE_DOCKER_SERVICES = os.environ.get("USE_DOCKER_SERVICES", "false").lower() == "true"
    USE_AWS = os.environ.get("USE_AWS", "false").lower() == "true"
    USE_ELASTICSEARCH = os.environ.get("USE_ELASTICSEARCH", "false").lower() == "true"
    # Allow dev form posts without JWT double-submit CSRF to unblock local testing
    JWT_COOKIE_CSRF_PROTECT = False
    # Allow cookies (session, JWT, remember) over HTTP during local development so CSRF/session works without HTTPS
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False
    JWT_COOKIE_SECURE = False
    # Use localhost for Redis in dev so Docker hostnames are not required on Windows
    REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
    ELASTICSEARCH_URL = os.environ.get("ELASTICSEARCH_URL", "http://127.0.0.1:9200")
    CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", REDIS_URL)
    CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)


class TestingConfig(BaseConfig):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")


class ProductionConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SAMESITE = "Lax"
    JWT_COOKIE_SAMESITE = "Lax"


def get_config(env: str):
    env = env.lower()
    if env == "production":
        return ProductionConfig
    if env == "testing":
        return TestingConfig
    return DevelopmentConfig
