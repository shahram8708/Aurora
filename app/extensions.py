import os
import time
import importlib
import importlib.util
from datetime import timedelta
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_bcrypt import Bcrypt
from flask_wtf import CSRFProtect
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_socketio import SocketIO
from flask_mail import Mail
from authlib.integrations.flask_client import OAuth
from celery import Celery
import redis

def _driver_available(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
        return True
    except Exception:
        return False


# Centralized extension instances to avoid circular imports

db = SQLAlchemy()
migrate = Migrate()
bcrypt = Bcrypt()
csrf = CSRFProtect()
jwt = JWTManager()
mail = Mail()
oauth = OAuth()
# Limiter uses remote address; can be swapped to user-specific key in JWT-protected routes
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per day", "50 per hour"])


def _resolve_socketio_mode() -> str:
    # Favor explicit env when supported; otherwise pick the first available driver and fall back to threading.
    env_mode = os.environ.get("SOCKETIO_ASYNC_MODE")
    valid_modes = {"eventlet", "gevent", "gevent_uwsgi", "threading", "asyncio"}
    if env_mode in valid_modes:
        if env_mode.startswith("gevent") and not _driver_available("gevent"):
            return "threading"
        if env_mode == "eventlet" and not _driver_available("eventlet"):
            return "threading"
        return env_mode

    for candidate in ("eventlet", "gevent"):
        if _driver_available(candidate):
            return candidate

    return "threading"


socketio_async_mode = _resolve_socketio_mode()
# Prefer eventlet/gevent when available; thread fallback avoids engineio ValueError when optional drivers are missing
# manage_session=False avoids Flask 3+ RequestContext.session setter errors; JWT handles auth
socketio = SocketIO(async_mode=socketio_async_mode, cors_allowed_origins="*", serve_client=True, manage_session=False)
celery = Celery(__name__)

# Lightweight in-memory fallback so local dev can run without Redis
class LocalRedisCache:
    def __init__(self):
        self._store: dict[str, tuple[object, float | None]] = {}

    @staticmethod
    def _ttl_seconds(ttl: int | float | timedelta) -> float:
        return float(ttl.total_seconds() if isinstance(ttl, timedelta) else ttl)

    def _expired(self, key: str) -> bool:
        if key not in self._store:
            return False
        value, expires_at = self._store[key]
        if expires_at is None:
            return False
        if time.time() > expires_at:
            self._store.pop(key, None)
            return True
        return False

    def set(self, key: str, value: object):
        self._store[key] = (value, None)
        return True

    def setex(self, key: str, ttl: int | float | timedelta, value: object):
        self._store[key] = (value, time.time() + self._ttl_seconds(ttl))
        return True

    def get(self, key: str):
        if self._expired(key):
            return None
        entry = self._store.get(key)
        return entry[0] if entry else None

    def delete(self, *keys: str):
        removed = 0
        for key in keys:
            if self._expired(key):
                continue
            if key in self._store:
                self._store.pop(key, None)
                removed += 1
        return removed

    def incr(self, key: str, amount: int = 1):
        current = int(self.get(key) or 0)
        current += amount
        self.set(key, current)
        return current

    def expire(self, key: str, ttl: int | float | timedelta):
        if key not in self._store:
            return False
        value, _ = self._store[key]
        self._store[key] = (value, time.time() + self._ttl_seconds(ttl))
        return True

    def setnx(self, key: str, value: object):
        if self.get(key) is None:
            self.set(key, value)
            return True
        return False

    def rpush(self, key: str, *values: object):
        if self._expired(key):
            self._store.pop(key, None)
        entry = self._store.get(key)
        if entry and isinstance(entry[0], list):
            current, expires_at = list(entry[0]), entry[1]
        else:
            current, expires_at = [], entry[1] if entry else None
        current.extend(values)
        self._store[key] = (current, expires_at)
        return len(current)

    def lrange(self, key: str, start: int, end: int):
        if self._expired(key):
            return []
        entry = self._store.get(key)
        if not entry or not isinstance(entry[0], list):
            return []
        items, _ = entry
        length = len(items)
        if length == 0:
            return []
        if start < 0:
            start = length + start
        if end < 0:
            end = length + end
        start = max(start, 0)
        end = min(end, length - 1)
        if start > end:
            return []
        return items[start : end + 1]

    def ltrim(self, key: str, start: int, end: int):
        if self._expired(key):
            self._store.pop(key, None)
            return 0
        entry = self._store.get(key)
        if not entry or not isinstance(entry[0], list):
            return 0
        items, expires_at = entry
        length = len(items)
        if length == 0:
            return 0
        if start < 0:
            start = length + start
        if end < 0:
            end = length + end
        start = max(start, 0)
        end = min(end, length - 1)
        trimmed = items[start : end + 1] if start <= end else []
        self._store[key] = (trimmed, expires_at)
        return len(trimmed)

    def sadd(self, key: str, *values: object):
        if self._expired(key):
            self._store.pop(key, None)
        entry = self._store.get(key)
        if entry and isinstance(entry[0], set):
            current, expires_at = set(entry[0]), entry[1]
        else:
            current, expires_at = set(), entry[1] if entry else None
        before = len(current)
        current.update(values)
        self._store[key] = (current, expires_at)
        return len(current) - before

    def smembers(self, key: str):
        if self._expired(key):
            return set()
        entry = self._store.get(key)
        if not entry or not isinstance(entry[0], set):
            return set()
        return set(entry[0])

    def sismember(self, key: str, value: object):
        if self._expired(key):
            return False
        entry = self._store.get(key)
        if not entry or not isinstance(entry[0], set):
            return False
        return value in entry[0]

    def srem(self, key: str, *values: object):
        if self._expired(key):
            self._store.pop(key, None)
            return 0
        entry = self._store.get(key)
        if not entry or not isinstance(entry[0], set):
            return 0
        current, expires_at = set(entry[0]), entry[1]
        removed = 0
        for v in values:
            if v in current:
                current.remove(v)
                removed += 1
        self._store[key] = (current, expires_at)
        return removed

    def publish(self, channel: str, payload: object):
        # In-memory dev mode just acknowledges the publish.
        return 1


# Redis client factory
def init_redis_client(url: str | None, enabled: bool = True):
    if not enabled or not url:
        return LocalRedisCache()
    return redis.Redis.from_url(url, decode_responses=True)


def init_celery(app):
    conf = {
        "task_default_queue": app.config["CELERY_TASK_DEFAULT_QUEUE"],
        "task_serializer": app.config["CELERY_TASK_SERIALIZER"],
        "accept_content": app.config["CELERY_ACCEPT_CONTENT"],
        "result_serializer": app.config["CELERY_RESULT_SERIALIZER"],
        "task_time_limit": app.config["CELERY_TASK_TIME_LIMIT"],
        "timezone": "UTC",
    }

    if app.config.get("USE_CELERY", True):
        conf.update(
            broker_url=app.config["CELERY_BROKER_URL"],
            result_backend=app.config["CELERY_RESULT_BACKEND"],
            task_always_eager=False,
        )
    else:
        conf.update(
            broker_url="memory://",
            result_backend="cache+memory://",
            task_always_eager=True,
            task_eager_propagates=True,
        )

    celery.conf.update(**conf)
    celery.conf.beat_schedule = {
        "refresh-trending-reels": {
            "task": "app.reels.tasks.refresh_trending",
            "schedule": 300,
        },
        "cleanup-expired-stories": {
            "task": "app.stories.tasks.cleanup_expired",
            "schedule": 600,
        },
        "refresh-explore-cache": {
            "task": "app.explore.tasks.refresh_explore_cache",
            "schedule": 300,
        },
        "refresh-trending-reels-advanced": {
            "task": "app.algorithms.tasks.refresh_trending_reels",
            "schedule": 300,
        },
        "sync-search-index": {
            "task": "app.algorithms.tasks.reindex_search",
            "schedule": 900,
        },
        "run-moderation-queue": {
            "task": "app.moderation.tasks.run_moderation_queue",
            "schedule": 120,
        },
        "send-live-reminders": {
            "task": "app.live.tasks.send_live_reminders",
            "schedule": 300,
        },
        "auto-activate-live": {
            "task": "app.live.tasks.auto_activate",
            "schedule": 60,
        },
        "refresh-analytics-cache": {
            "task": "app.business.tasks.refresh_cached_insights",
            "schedule": 900,
        },
        "process-payout-queue": {
            "task": "app.payments.tasks.process_pending_payouts",
            "schedule": 600,
        },
        "recompute-live-earnings": {
            "task": "app.monetization.tasks.recompute_live_earnings",
            "schedule": 600,
        },
        "expire-inventory-reservations": {
            "task": "app.commerce.expire_inventory_reservations_task",
            "schedule": 300,
        },
    }

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):  # type: ignore[override]
            with app.app_context():
                return super().__call__(*args, **kwargs)

    celery.Task = ContextTask
    celery.autodiscover_tasks([
        "app.reels",
        "app.stories",
        "app.recommendation",
        "app.notifications",
        "app.explore",
        "app.algorithms",
        "app.moderation",
        "app.live",
        "app.business",
        "app.monetization",
        "app.payments",
        "app.commerce",
        "app.orders",
        "app.shop",
        "app.affiliate",
        "app.settings",
        "app.email",
    ])
    return celery
