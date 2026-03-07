import logging
import requests
from flask import current_app
from app.algorithms.recommendation_cache import cache_get, cache_set

logger = logging.getLogger(__name__)


class AIContentService:
    def __init__(self):
        self.endpoint = current_app.config.get("AI_CONTENT_API_URL")
        self.api_key = current_app.config.get("AI_CONTENT_API_KEY")
        self.cache_ttl = current_app.config.get("AI_CONTENT_CACHE_TTL", 86400)

    def suggest_caption(self, media_metadata: dict):
        cache_key = f"ai:caption:{hash(str(media_metadata))}"
        cached = cache_get(cache_key)
        if cached:
            return cached
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            resp = requests.post(self.endpoint, json=media_metadata, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            cache_set(cache_key, data, ttl=self.cache_ttl)
            return data
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("ai suggestion failed", exc_info=exc)
            return {}

    def suggest_reel_enhancements(self, insight: dict):
        # Heuristic-based suggestions when AI API unavailable
        duration = insight.get("duration_seconds", 0)
        avg_watch = insight.get("avg_watch_time", 0)
        completion_rate = avg_watch / duration if duration else 0
        suggestions = {
            "optimal_length": 15 if duration > 30 else duration,
            "caption": "Keep captions under 100 characters for better retention",
            "music": "Trending upbeat tracks recommended",
            "hashtags": ["fyp", "trending", "recommended"],
            "completion_rate": round(completion_rate, 2),
        }
        cache_set(f"ai:reel:{hash(str(insight))}", suggestions, ttl=self.cache_ttl)
        return suggestions


def ai_content_service() -> AIContentService:
    return AIContentService()
