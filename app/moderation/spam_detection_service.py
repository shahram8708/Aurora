from datetime import datetime, timedelta
from sqlalchemy import func
from flask import current_app
from app.extensions import db
from app.models import Post, Reel, Hashtag, PostHashtag, Follow, Like


class SpamDetectionService:
    def _rapid_posting_score(self, user_id):
        window = datetime.utcnow() - timedelta(hours=1)
        post_count = db.session.query(func.count(Post.id)).filter(Post.user_id == user_id, Post.created_at >= window).scalar() or 0
        reel_count = db.session.query(func.count(Reel.id)).filter(Reel.user_id == user_id, Reel.created_at >= window).scalar() or 0
        return min((post_count + reel_count) / 5.0, 1.0)

    def _duplicate_caption_score(self, caption: str, user_id):
        if not caption:
            return 0
        recent = db.session.query(func.count(Post.id)).filter(Post.user_id == user_id, func.similarity(Post.caption, caption) > 0.9).scalar() or 0
        return min(recent / 3.0, 1.0)

    def _hashtag_abuse_score(self, post_id):
        count = db.session.query(func.count(PostHashtag.hashtag_id)).filter(PostHashtag.post_id == post_id).scalar() or 0
        return min(count / 30.0, 1.0)

    def _like_velocity_score(self, post_id):
        window = datetime.utcnow() - timedelta(minutes=30)
        likes = db.session.query(func.count(Like.id)).filter(Like.post_id == post_id, Like.created_at >= window).scalar() or 0
        return min(likes / 50.0, 1.0)

    def score_post(self, post: Post) -> float:
        score = 0
        score += self._rapid_posting_score(post.user_id) * 0.3
        score += self._duplicate_caption_score(post.caption or "", post.user_id) * 0.2
        score += self._hashtag_abuse_score(post.id) * 0.2
        score += self._like_velocity_score(post.id) * 0.3
        return round(score, 3)

    def score_reel(self, reel: Reel) -> float:
        score = 0
        score += self._rapid_posting_score(reel.user_id) * 0.4
        score += self._duplicate_caption_score(reel.caption or "", reel.user_id) * 0.2
        score += self._like_velocity_score(reel.id) * 0.4
        return round(score, 3)


spam_detection_service = SpamDetectionService()
