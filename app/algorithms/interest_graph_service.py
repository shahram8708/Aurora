from datetime import datetime
import uuid
from typing import Iterable
from sqlalchemy import func
from app.extensions import db
from app.models import InterestGraph, Hashtag, PostHashtag


class InterestGraphService:
    def interest_subquery(self, user_id: str):
        user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
        return db.session.query(InterestGraph.tag_id.label("tag_id"), InterestGraph.weight.label("weight")).filter(InterestGraph.user_id == user_uuid).subquery()

    def increment_weights(self, user_id: str, hashtag_ids: Iterable[int], weight: float = 0.1):
        user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
        now = datetime.utcnow()
        for tag_id in set(hashtag_ids):
            existing = InterestGraph.query.filter_by(user_id=user_uuid, tag_id=tag_id).first()
            if existing:
                existing.weight = func.least(existing.weight + weight, 10.0)
                existing.last_updated = now
            else:
                db.session.add(InterestGraph(user_id=user_uuid, tag_id=tag_id, weight=weight, last_updated=now))
        db.session.commit()

    def decay_all(self, decay_factor: float = 0.98):
        db.session.query(InterestGraph).update({InterestGraph.weight: InterestGraph.weight * decay_factor})
        db.session.commit()

    def learn_from_post(self, user_id: str, post_id):
        user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
        hashtag_ids = [row[0] for row in db.session.query(PostHashtag.hashtag_id).filter(PostHashtag.post_id == post_id).all()]
        if hashtag_ids:
            self.increment_weights(user_uuid, hashtag_ids, weight=0.2)


interest_graph_service = InterestGraphService()
