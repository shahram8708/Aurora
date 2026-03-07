from datetime import datetime, timedelta
from sqlalchemy import func
from app.extensions import db
from app.models import User, Follow, Post, Like, Message


class BotDetectionService:
    def follow_rate(self, user_id):
        window = datetime.utcnow() - timedelta(hours=1)
        count = db.session.query(func.count(Follow.id)).filter(Follow.follower_id == user_id, Follow.created_at >= window).scalar() or 0
        return min(count / 50.0, 1.0)

    def engagement_ratio(self, user_id):
        posts = db.session.query(func.count(Post.id)).filter(Post.user_id == user_id).scalar() or 1
        likes = db.session.query(func.count(Like.id)).filter(Like.user_id == user_id).scalar() or 0
        return max(0, 1 - (likes / posts) * 0.1)

    def message_spam_frequency(self, user_id):
        try:
            count = db.session.query(func.count(Message.id)).filter(Message.sender_id == user_id, Message.created_at >= datetime.utcnow() - timedelta(hours=1)).scalar()
        except Exception:
            count = 0
        return min((count or 0) / 100.0, 1.0)

    def account_age_ratio(self, user: User):
        days = (datetime.utcnow() - user.created_at).days or 1
        activity = (user.follower_count + user.following_count) or 1
        return min(activity / days / 50.0, 1.0)

    def bot_probability(self, user: User) -> float:
        prob = 0
        prob += self.follow_rate(user.id) * 0.3
        prob += self.engagement_ratio(user.id) * 0.25
        prob += self.message_spam_frequency(user.id) * 0.2
        prob += self.account_age_ratio(user) * 0.25
        return round(min(prob, 1.0), 3)


bot_detection_service = BotDetectionService()
