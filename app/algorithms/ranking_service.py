from datetime import datetime, timedelta
import uuid
from typing import List, Optional, Sequence
from flask import current_app
from sqlalchemy import func, desc, case, literal_column
from sqlalchemy.orm import aliased
from app.extensions import db
from app.models import (
    Post,
    Reel,
    ReelInsight,
    User,
    Hashtag,
    PostHashtag,
    Follow,
    Block,
    Mute,
    Like,
    Comment,
    InterestGraph,
)
from .interest_graph_service import InterestGraphService

RECENCY_HALF_LIFE_HOURS = 12
CREATOR_QUALITY_HALF_LIFE_DAYS = 30


def recency_decay(column):
    age_hours = func.extract("epoch", func.now() - column) / 3600.0
    return func.exp(-age_hours / RECENCY_HALF_LIFE_HOURS)


def creator_quality(user_alias):
    cols = user_alias.c if hasattr(user_alias, "c") else user_alias
    # SQLite lacks LEAST; use MIN to cap the ratio at 10
    follower_component = func.min(func.coalesce(cols.follower_count, 0) / func.nullif(cols.following_count + 1, 0), 10)
    verification_bonus = case((cols.is_verified.is_(True), 2), else_=0)
    recent_activity = func.exp(-func.extract("epoch", func.now() - cols.updated_at) / (CREATOR_QUALITY_HALF_LIFE_DAYS * 86400.0))
    return follower_component + verification_bonus + recent_activity


def normalize_engagement(like_count, comment_count, share_count, watch_time, impressions):
    weighted = like_count * 1.0 + comment_count * 2.0 + share_count * 3.0 + watch_time * 0.001
    return weighted / func.nullif(impressions, 1)


class RankingService:
    def __init__(self):
        self.interest = InterestGraphService()

    def explore_posts(self, user_id: str, limit: int = 30, offset: int = 0, category: Optional[str] = None) -> Sequence[Post]:
        user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))

        blocked = db.session.query(Block.target_id).filter(Block.user_id == user_uuid)
        blocked_by = db.session.query(Block.user_id).filter(Block.target_id == user_uuid)
        muted = db.session.query(Mute.target_id).filter(Mute.user_id == user_uuid)
        following = db.session.query(Follow.following_id).filter(Follow.follower_id == user_uuid)
        interest_weights = self.interest.interest_subquery(user_uuid)
        ph = aliased(PostHashtag)
        ht = aliased(Hashtag)
        user_alias = aliased(User)
        like_counts = db.session.query(Like.post_id, func.count(Like.id).label("like_count")).group_by(Like.post_id).subquery()
        comment_counts = db.session.query(Comment.post_id, func.count(Comment.id).label("comment_count")).group_by(Comment.post_id).subquery()

        base = (
            db.session.query(
                Post,
                func.coalesce(like_counts.c.like_count, 0).label("likes"),
                func.coalesce(comment_counts.c.comment_count, 0).label("comments"),
                recency_decay(Post.created_at).label("recency"),
                func.coalesce(func.sum(interest_weights.c.weight), 0).label("interest_match"),
                creator_quality(user_alias).label("creator_quality"),
            )
            .join(user_alias, user_alias.id == Post.user_id)
            .outerjoin(like_counts, like_counts.c.post_id == Post.id)
            .outerjoin(comment_counts, comment_counts.c.post_id == Post.id)
            .outerjoin(ph, ph.post_id == Post.id)
            .outerjoin(ht, ht.id == ph.hashtag_id)
            .outerjoin(interest_weights, interest_weights.c.tag_id == ph.hashtag_id)
            .filter(Post.is_archived.is_(False))
            .filter(Post.is_sensitive.is_(False))
            .filter(~Post.user_id.in_(blocked))
            .filter(~Post.user_id.in_(blocked_by))
            .filter(~Post.user_id.in_(muted))
            .filter((user_alias.is_private.is_(False)) | (Post.user_id.in_(following)) | (Post.user_id == user_uuid))
        )

        if category:
            base = base.filter(user_alias.category == category)

        engagement_score = normalize_engagement(literal_column("likes"), literal_column("comments"), literal_column("0"), literal_column("0"), literal_column("1"))
        score_expr = (
            engagement_score * 0.4
            + literal_column("recency") * 0.2
            + literal_column("interest_match") * 0.3
            + literal_column("creator_quality") * 0.1
        )

        rows = (
            base.group_by(Post.id, user_alias.id, user_alias.follower_count, user_alias.following_count, user_alias.is_verified, user_alias.updated_at)
            .order_by(desc(score_expr))
            .limit(limit)
            .offset(offset)
            .all()
        )
        return [r[0] for r in rows]

    def explore_reels(self, user_id: str, limit: int = 30) -> Sequence[Reel]:
        user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))

        blocked = db.session.query(Block.target_id).filter(Block.user_id == user_uuid)
        blocked_by = db.session.query(Block.user_id).filter(Block.target_id == user_uuid)
        muted = db.session.query(Mute.target_id).filter(Mute.user_id == user_uuid)
        following = db.session.query(Follow.following_id).filter(Follow.follower_id == user_uuid) if user_id else db.session.query(Follow.following_id).filter(False)
        user_alias = aliased(User)

        score = (
            func.coalesce(ReelInsight.view_count, 0) * 1.5
            + func.coalesce(ReelInsight.like_count, 0) * 2.0
            + func.coalesce(ReelInsight.comment_count, 0) * 2.5
            + func.coalesce(ReelInsight.share_count, 0) * 3.0
            + recency_decay(Reel.created_at) * 5
            + creator_quality(user_alias)
        )

        rows = (
            db.session.query(Reel)
            .outerjoin(ReelInsight, ReelInsight.reel_id == Reel.id)
            .join(user_alias, user_alias.id == Reel.user_id)
            .filter(Reel.is_published.is_(True))
            .filter(Reel.is_sensitive.is_(False))
            .filter(~Reel.user_id.in_(blocked))
            .filter(~Reel.user_id.in_(blocked_by))
            .filter(~Reel.user_id.in_(muted))
            .filter((user_alias.is_private.is_(False)) | (Reel.user_id.in_(following)) | (Reel.user_id == user_uuid))
            .order_by(desc(score))
            .limit(limit)
            .all()
        )
        return rows

    def suggested_accounts(self, user_id: str, limit: int = 15) -> Sequence[User]:
        user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))

        following = db.session.query(Follow.following_id).filter(Follow.follower_id == user_uuid)
        mutuals = (
            db.session.query(Follow.following_id.label("candidate"), func.count().label("mutuals"))
            .filter(Follow.follower_id.in_(following))
            .group_by(Follow.following_id)
            .subquery()
        )
        ig = self.interest.interest_subquery(user_uuid)

        score = (
            func.coalesce(mutuals.c.mutuals, 0) * 3
            + func.coalesce(ig.c.weight, 0) * 2
            + func.coalesce(User.follower_count, 0) * 0.01
        )

        q = (
            db.session.query(User)
            .outerjoin(mutuals, mutuals.c.candidate == User.id)
            .outerjoin(ig, literal_column("1") == literal_column("1"))
            .filter(User.id != user_uuid)
            .filter(~User.id.in_(following))
            .filter(User.is_active.is_(True))
            .filter(User.is_private.is_(False))
            .order_by(desc(score))
            .limit(limit)
        )
        return q.all()

    def suggested_hashtags(self, user_id: str, limit: int = 10) -> Sequence[Hashtag]:
        ig = self.interest.interest_subquery(user_id)
        q = (
            db.session.query(Hashtag)
            .join(ig, ig.c.tag_id == Hashtag.id)
            .order_by(desc(ig.c.weight))
            .limit(limit)
        )
        return q.all()


ranking_service = RankingService()
