import logging
from typing import Dict, Optional
import requests
from flask import current_app
from app.extensions import db
from app.models import ModerationEvent, Post, Reel

logger = logging.getLogger(__name__)


class ModerationService:
    def __init__(self):
        self.endpoint = current_app.config["MODERATION_API_URL"]
        self.api_key = current_app.config.get("MODERATION_API_KEY")

    def analyze(self, content_type: str, content_id: str, payload: Dict) -> ModerationEvent:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        data = {"content_type": content_type, "payload": payload}
        try:
            resp = requests.post(self.endpoint, json=data, headers=headers, timeout=8)
            resp.raise_for_status()
            result = resp.json()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("moderation call failed", exc_info=exc)
            result = {"status": "error", "reason": str(exc)}

        score = result.get("score") if isinstance(result, dict) else None
        flagged = bool(result.get("flagged")) if isinstance(result, dict) else False
        action = result.get("action", "allow") if isinstance(result, dict) else "review"
        event = ModerationEvent(
            content_type=content_type,
            content_id=content_id,
            provider="external",
            result=result,
            score=score,
            action=action,
            is_flagged=flagged,
            reason=result.get("reason") if isinstance(result, dict) else None,
        )
        db.session.add(event)
        self._apply_side_effects(content_type, content_id, flagged, result)
        db.session.commit()
        return event

    def _apply_side_effects(self, content_type: str, content_id: str, flagged: bool, result: Dict):
        if content_type == "post":
            q = Post.query.filter_by(id=content_id)
            updates = {"is_sensitive": flagged, "moderation_result": result}
            q.update(updates)
        elif content_type == "reel":
            q = Reel.query.filter_by(id=content_id)
            updates = {"is_sensitive": flagged, "moderation_result": result}
            q.update(updates)

    def mark_sensitive(self, content_type: str, content_id: str, reason: str):
        event = ModerationEvent(
            content_type=content_type,
            content_id=content_id,
            provider="manual",
            result={"reason": reason},
            score=1.0,
            action="hide",
            is_flagged=True,
        )
        db.session.add(event)
        self._apply_side_effects(content_type, content_id, True, {"reason": reason})
        db.session.commit()
        return event


def moderation_service() -> ModerationService:
    return ModerationService()
