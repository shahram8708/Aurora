import json
from typing import Any, Callable, Optional
from flask import current_app
from app.extensions import db


def cache_get(key: str):
    raw = current_app.redis_client.get(key)
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return None


def cache_set(key: str, value: Any, ttl: Optional[int] = None):
    ttl = ttl or current_app.config["EXPLORE_CACHE_TTL"]
    current_app.redis_client.setex(key, ttl, json.dumps(value))


def cached(key: str, loader: Callable[[], Any], ttl: Optional[int] = None):
    val = cache_get(key)
    if val is not None:
        return val
    data = loader()
    cache_set(key, data, ttl)
    return data
