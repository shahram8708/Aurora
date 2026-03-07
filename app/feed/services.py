from datetime import datetime, timedelta
import uuid
from sqlalchemy import func, case, desc
from sqlalchemy.orm import selectinload
from app.extensions import db
from app.models import Post, Like, Comment, Follow, Block, AdCampaign
from app.business.ads_tracking import record_impressions

RECENCY_HALF_LIFE_HOURS = 24


def _recency_weight(created_at):
    age_hours = func.extract("epoch", func.now() - created_at) / 3600.0
    return func.exp(-age_hours / RECENCY_HALF_LIFE_HOURS) * 10


def _relationship_weight(user_id):
    return case((Follow.follower_id == user_id, 5), else_=0)


def fetch_feed(user_id: str, limit: int = 10, offset: int = 0):
    # Ensure UUID objects are passed to SQLAlchemy UUID columns
    try:
        user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
    except (ValueError, TypeError, AttributeError):
        return []

    blocked = db.session.query(Block.target_id).filter(Block.user_id == user_uuid)
    blocked_by = db.session.query(Block.user_id).filter(Block.target_id == user_uuid)

    like_counts = db.session.query(Like.post_id, func.count(Like.id).label("like_count")).group_by(Like.post_id).subquery()
    comment_counts = db.session.query(Comment.post_id, func.count(Comment.id).label("comment_count")).group_by(Comment.post_id).subquery()

    follow_alias = (
        db.session.query(Follow.following_id.label("following_id"))
        .filter(Follow.follower_id == user_uuid)
        .subquery()
    )

    base = (
        db.session.query(
            Post,
            func.coalesce(like_counts.c.like_count, 0).label("like_count"),
            func.coalesce(comment_counts.c.comment_count, 0).label("comment_count"),
            _recency_weight(Post.created_at).label("recency"),
            _relationship_weight(user_uuid).label("relationship"),
        )
        .outerjoin(like_counts, like_counts.c.post_id == Post.id)
        .outerjoin(comment_counts, comment_counts.c.post_id == Post.id)
        .outerjoin(Follow, Follow.following_id == Post.user_id)
        .filter(Post.is_archived.is_(False))
        .filter(~Post.user_id.in_(blocked))
        .filter(~Post.user_id.in_(blocked_by))
        .filter((Post.user_id == user_uuid) | (Post.user_id.in_(follow_alias)))
    )

    score_expr = (
        func.coalesce(like_counts.c.like_count, 0) * 3
        + func.coalesce(comment_counts.c.comment_count, 0) * 5
        + _recency_weight(Post.created_at)
        + _relationship_weight(user_uuid)
    )

    posts_rows = (
        base.order_by(desc(score_expr))
        .limit(limit)
        .offset(offset)
        .options(
            selectinload(Post.media),
            selectinload(Post.likes).selectinload(Like.user),
            selectinload(Post.comments).selectinload(Comment.user),
            selectinload(Post.hashtags),
            selectinload(Post.user),
        )
        .all()
    )
    posts = [row[0] for row in posts_rows]

    # If the user follows no one (or has no posts), fall back to public feed ordered by recency/engagement
    if not posts:
        fallback_rows = (
            db.session.query(
                Post,
                func.coalesce(like_counts.c.like_count, 0).label("like_count"),
                func.coalesce(comment_counts.c.comment_count, 0).label("comment_count"),
            )
            .outerjoin(like_counts, like_counts.c.post_id == Post.id)
            .outerjoin(comment_counts, comment_counts.c.post_id == Post.id)
            .filter(Post.is_archived.is_(False))
            .filter(~Post.user_id.in_(blocked))
            .filter(~Post.user_id.in_(blocked_by))
            .order_by(desc(_recency_weight(Post.created_at) + func.coalesce(like_counts.c.like_count, 0) + func.coalesce(comment_counts.c.comment_count, 0)))
            .limit(limit)
            .offset(offset)
            .options(
                selectinload(Post.media),
                selectinload(Post.likes).selectinload(Like.user),
                selectinload(Post.comments).selectinload(Comment.user),
                selectinload(Post.hashtags),
                selectinload(Post.user),
            )
            .all()
        )
        posts = [row[0] for row in fallback_rows]

    # annotate promoted posts from paid campaigns within active dates
    post_ids = [p.id for p in posts if p.id]
    if post_ids:
        today = datetime.utcnow()
        campaigns = (
            db.session.query(AdCampaign)
            .filter(
                AdCampaign.post_id.in_(post_ids),
                AdCampaign.status == "paid",
                AdCampaign.start_date <= today,
                AdCampaign.end_date >= today,
            )
            .all()
        )
        cmap = {c.post_id: c for c in campaigns}
        promoted_campaigns = []
        for p in posts:
            camp = cmap.get(p.id)
            if camp:
                setattr(p, "is_promoted", True)
                setattr(p, "promoted_label", "Promoted")
                setattr(p, "promoted_order_id", camp.razorpay_order_id)
                promoted_campaigns.append(camp)
        if promoted_campaigns:
            record_impressions(promoted_campaigns, user_uuid)
        return posts

    # No campaigns to annotate; still return posts to avoid None
    return posts
