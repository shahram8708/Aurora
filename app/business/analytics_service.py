from datetime import datetime
import uuid
from flask import current_app
from sqlalchemy import func
from app.extensions import db
from app.models import (
    Post,
    Like,
    Comment,
    Reel,
    ReelInsight,
    Story,
    StoryInsight,
    StoryView,
    Follow,
    LiveSession,
    LiveParticipant,
    AdsRevenue,
    RevenueAggregate,
    AudienceDemographic,
)


def _cache_key(user_id: str, start: datetime, end: datetime) -> str:
    return f"analytics:{user_id}:{start.date()}:{end.date()}"


def _as_uuid(user_id):
    return user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))


def get_insights(user_id: str, start: datetime, end: datetime) -> dict:
    user_uuid = _as_uuid(user_id)
    client = getattr(current_app, "redis_client", None)
    cache_ttl = current_app.config.get("ANALYTICS_CACHE_TTL", 900)
    key = _cache_key(user_id, start, end)
    if client:
        cached = client.get(key)
        if cached:
            import json

            return json.loads(cached)

    reach = (
        db.session.query(func.count(func.distinct(StoryView.viewer_id)))
        .select_from(Story)
        .join(StoryView, StoryView.story_id == Story.id)
        .filter(Story.user_id == user_uuid, Story.created_at.between(start, end))
        .scalar()
        or 0
    )
    impressions = (
        db.session.query(func.coalesce(func.sum(StoryInsight.view_count), 0))
        .join(Story, StoryInsight.story_id == Story.id)
        .filter(Story.user_id == user_uuid, Story.created_at.between(start, end))
        .scalar()
        or 0
    )
    reel_views = (
        db.session.query(func.coalesce(func.sum(ReelInsight.view_count), 0))
        .join(Reel, ReelInsight.reel_id == Reel.id)
        .filter(Reel.user_id == user_uuid, Reel.created_at.between(start, end))
        .scalar()
        or 0
    )
    story_views = impressions
    live_views = (
        db.session.query(func.count(LiveParticipant.user_id))
        .join(LiveSession, LiveSession.id == LiveParticipant.session_id)
        .filter(LiveSession.host_id == user_uuid, LiveSession.created_at.between(start, end))
        .scalar()
        or 0
    )
    follower_growth = (
        db.session.query(func.count(Follow.id))
        .filter(Follow.following_id == user_uuid, Follow.created_at.between(start, end))
        .scalar()
        or 0
    )
    likes = (
        db.session.query(func.count(Like.id))
        .join(Post, Post.id == Like.post_id)
        .filter(Post.user_id == user_uuid, Post.created_at.between(start, end))
        .scalar()
        or 0
    )
    comments = (
        db.session.query(func.count(Comment.id))
        .join(Post, Post.id == Comment.post_id)
        .filter(Post.user_id == user_uuid, Post.created_at.between(start, end))
        .scalar()
        or 0
    )
    total_engagements = likes + comments
    engagement_rate = float(total_engagements) / max(reel_views + impressions, 1)

    revenue_rows = (
        db.session.query(
            func.coalesce(func.sum(RevenueAggregate.earnings), 0),
            func.coalesce(func.sum(RevenueAggregate.platform_fees), 0),
        )
        .filter(RevenueAggregate.creator_id == user_uuid, RevenueAggregate.date.between(start.date(), end.date()))
        .first()
    )
    revenue = revenue_rows[0] if revenue_rows else 0
    platform_fees = revenue_rows[1] if revenue_rows else 0

    demographics = (
        db.session.query(
            AudienceDemographic.age_group,
            AudienceDemographic.gender,
            AudienceDemographic.country,
            AudienceDemographic.city,
            AudienceDemographic.count,
        )
        .filter(AudienceDemographic.creator_id == user_uuid)
        .all()
    )
    audience = [
        {
            "age_group": row.age_group,
            "gender": row.gender,
            "country": row.country,
            "city": row.city,
            "count": row.count,
        }
        for row in demographics
    ]

    data = {
        "reach": reach,
        "impressions": impressions,
        "engagement_rate": engagement_rate,
        "follower_growth": follower_growth,
        "reel_views": reel_views,
        "story_views": story_views,
        "live_views": live_views,
        "revenue": revenue,
        "platform_fees": platform_fees,
        "audience": audience,
    }
    if client:
        import json

        client.setex(key, cache_ttl, json.dumps(data))
    return data


def content_analytics(user_id: str):
    user_uuid = _as_uuid(user_id)
    reels = (
        db.session.query(Reel.id, Reel.caption, ReelInsight.view_count, ReelInsight.like_count, ReelInsight.comment_count, ReelInsight.watch_time)
        .join(ReelInsight, ReelInsight.reel_id == Reel.id)
        .filter(Reel.user_id == user_uuid)
        .all()
    )
    posts = (
        db.session.query(Post.id, Post.caption, func.count(Like.id).label("likes"), func.count(Comment.id).label("comments"))
        .join(Like, Like.post_id == Post.id, isouter=True)
        .join(Comment, Comment.post_id == Post.id, isouter=True)
        .filter(Post.user_id == user_uuid)
        .group_by(Post.id)
        .all()
    )
    return {
        "reels": [
            {
                "id": str(r.id),
                "caption": r.caption,
                "views": r.view_count,
                "engagement_rate": float(r.like_count + r.comment_count) / max(r.view_count, 1),
                "watch_time": r.watch_time,
            }
            for r in reels
        ],
        "posts": [
            {
                "id": str(p.id),
                "caption": p.caption,
                "engagement_rate": float(p.likes + p.comments) / max(p.likes + p.comments, 1),
            }
            for p in posts
        ],
    }


def ads_performance(user_id: str):
    creator_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
    rows = (
        db.session.query(
            func.coalesce(func.sum(AdsRevenue.impressions), 0),
            func.coalesce(func.sum(AdsRevenue.clicks), 0),
            func.coalesce(func.sum(AdsRevenue.earnings), 0),
            func.coalesce(func.sum(AdsRevenue.platform_fees), 0),
        )
        .filter(AdsRevenue.creator_id == creator_uuid)
        .first()
    )
    return {
        "impressions": rows[0] if rows else 0,
        "clicks": rows[1] if rows else 0,
        "earnings": rows[2] if rows else 0,
        "platform_fees": rows[3] if rows else 0,
    }
