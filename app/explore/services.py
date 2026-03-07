import random
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from flask import current_app
from sqlalchemy import func, desc
from app.extensions import db
from app.models import Post, Reel, ReelInsight, User, Hashtag, Follow, AdCampaign
from app.recommendation.services import annotate_promoted_reels
from app.algorithms.ranking_service import ranking_service
from app.algorithms.recommendation_cache import cache_get, cache_set
from app.business.ads_tracking import record_impressions


class ExploreFeedService:
    def __init__(self):
        self.cache_ttl = current_app.config["EXPLORE_CACHE_TTL"]

    def trending_reels(self, limit: int = 20) -> List[Reel]:
        cached = cache_get("trending:reels")
        if cached:
            # Ensure cached IDs are UUID objects to satisfy the UUID column binder
            order_ids = []
            for raw in cached:
                try:
                    order_ids.append(raw if isinstance(raw, uuid.UUID) else uuid.UUID(str(raw)))
                except (ValueError, TypeError, AttributeError):
                    continue

            if order_ids:
                order_index = {rid: idx for idx, rid in enumerate(order_ids)}
                reels = (
                    Reel.query.join(User, User.id == Reel.user_id)
                    .filter(User.is_private.is_(False))
                    .filter(Reel.id.in_(order_ids))
                    .all()
                )
                reels = sorted(
                    [r for r in reels if not r.user.is_private],
                    key=lambda r: order_index.get(r.id, len(order_index)),
                )
                return reels[:limit]

        now = datetime.utcnow()
        # SQLite lacks GREATEST; use MIN/MAX pattern to cap lower bound at 1 hour
        hours_live = func.max(func.extract("epoch", func.now() - Reel.created_at) / 3600.0, 1.0)
        velocity = func.coalesce(ReelInsight.view_count / hours_live, 0)
        score = (
            velocity * 3
            + func.coalesce(ReelInsight.share_count, 0) * 5
            + func.coalesce(ReelInsight.comment_count, 0) * 4
            + func.exp(-func.extract("epoch", func.now() - Reel.created_at) / 7200.0)
        )
        rows = (
            db.session.query(Reel)
            .outerjoin(ReelInsight, ReelInsight.reel_id == Reel.id)
            .join(User, User.id == Reel.user_id)
            .filter(Reel.is_published.is_(True))
            .filter(User.is_private.is_(False))
            .order_by(desc(score))
            .limit(limit)
            .all()
        )
        cache_set("trending:reels", [str(r.id) for r in rows], self.cache_ttl)
        return rows

    def trending_posts(self, limit: int = 20) -> List[Post]:
        cached = cache_get("trending:posts")
        if cached:
            order = cached
            posts = (
                Post.query.join(User, User.id == Post.user_id)
                .filter(User.is_private.is_(False))
                .filter(Post.id.in_(order))
                .all()
            )
            posts = sorted([p for p in posts if not p.user.is_private], key=lambda p: order.index(str(p.id)))
            return posts[:limit]
        like_counts = db.session.query(Post.id.label("pid"), func.count().label("like_count")).join(Post.likes).group_by(Post.id).subquery()
        comment_counts = db.session.query(Post.id.label("pid"), func.count().label("comment_count")).join(Post.comments).group_by(Post.id).subquery()
        score = (
            func.coalesce(like_counts.c.like_count, 0) * 2
            + func.coalesce(comment_counts.c.comment_count, 0) * 3
            + func.exp(-func.extract("epoch", func.now() - Post.created_at) / 86400.0)
        )
        rows = (
            db.session.query(Post)
            .outerjoin(like_counts, like_counts.c.pid == Post.id)
            .outerjoin(comment_counts, comment_counts.c.pid == Post.id)
            .join(User, User.id == Post.user_id)
            .filter(Post.is_archived.is_(False))
            .filter(Post.is_sensitive.is_(False))
            .filter(User.is_private.is_(False))
            .order_by(desc(score))
            .limit(limit)
            .all()
        )
        cache_set("trending:posts", [str(p.id) for p in rows], self.cache_ttl)
        return rows

    def suggested_accounts(self, user_id: str, limit: int = 10) -> List[User]:
        return list(ranking_service.suggested_accounts(user_id, limit=limit))

    def suggested_hashtags(self, user_id: str, limit: int = 10) -> List[Hashtag]:
        return list(ranking_service.suggested_hashtags(user_id, limit=limit))

    def category_discovery(self, category: Optional[str] = None, limit: int = 12) -> List[User]:
        q = User.query.filter(User.is_private.is_(False)).filter(User.is_active.is_(True))
        if category:
            q = q.filter(User.category == category)
        return q.order_by(desc(User.follower_count)).limit(limit).all()

    def explore_feed(self, user_id: str, limit: int = 30, offset: int = 0, category: Optional[str] = None) -> Dict[str, List]:
        posts = list(ranking_service.explore_posts(user_id, limit=limit, offset=offset, category=category))
        reels = list(ranking_service.explore_reels(user_id, limit=limit))
        viewer_uuid = None
        try:
            viewer_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id)) if user_id else None
        except (ValueError, TypeError, AttributeError):
            viewer_uuid = None

        post_ids = [p.id for p in posts if getattr(p, "id", None)]
        promoted_campaigns = []
        if post_ids:
            now = datetime.utcnow()
            campaigns = (
                db.session.query(AdCampaign)
                .filter(
                    AdCampaign.post_id.in_(post_ids),
                    AdCampaign.status == "paid",
                    AdCampaign.start_date <= now,
                    AdCampaign.end_date >= now,
                )
                .all()
            )
            cmap = {c.post_id: c for c in campaigns}
            for post in posts:
                camp = cmap.get(post.id)
                if camp:
                    setattr(post, "is_promoted", True)
                    setattr(post, "promoted_label", "Promoted")
                    setattr(post, "promoted_order_id", camp.razorpay_order_id)
                    promoted_campaigns.append(camp)
        random.shuffle(posts)
        random.shuffle(reels)
        annotate_promoted_reels(reels, viewer_id=viewer_uuid)
        trending = annotate_promoted_reels(self.trending_reels(limit=10), viewer_id=viewer_uuid)
        if promoted_campaigns:
            record_impressions(promoted_campaigns, viewer_uuid)
        suggested_accounts = self.suggested_accounts(user_id, limit=8)
        hashtags = self.suggested_hashtags(user_id, limit=8)
        return {
            "posts": posts,
            "reels": reels,
            "trending_reels": trending,
            "suggested_accounts": suggested_accounts,
            "hashtags": hashtags,
        }

    def cache_global(self):
        self.trending_posts()
        self.trending_reels()


def explore_service() -> ExploreFeedService:
    return ExploreFeedService()
