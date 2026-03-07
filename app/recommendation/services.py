import json
import uuid
from datetime import datetime
from flask import current_app
from sqlalchemy import func, desc, case
from sqlalchemy.orm import selectinload
from app.extensions import db
from app.models import Reel, ReelInsight, Follow, Block, User, AdCampaign
from app.business.ads_tracking import record_impressions


def _recency_weight(created_at):
    hours = func.extract("epoch", func.now() - created_at) / 3600.0
    return func.exp(-hours / 24.0) * 20


def compute_trending(limit=30):
    score = (
        func.coalesce(ReelInsight.view_count, 0) * 2
        + func.coalesce(ReelInsight.like_count, 0) * 3
        + func.coalesce(ReelInsight.comment_count, 0) * 4
        + func.coalesce(ReelInsight.share_count, 0) * 5
        + _recency_weight(Reel.created_at)
    )
    reels = (
        db.session.query(Reel)
        .outerjoin(ReelInsight, ReelInsight.reel_id == Reel.id)
        .filter(Reel.is_published.is_(True))
        .order_by(desc(score))
        .limit(limit)
        .options(selectinload(Reel.music), selectinload(Reel.stickers), selectinload(Reel.effects))
        .all()
    )
    payload = [str(r.id) for r in reels]
    current_app.redis_client.setex("cache:trending_reels", current_app.config["TRENDING_CACHE_TTL"], json.dumps(payload))
    return reels


def annotate_promoted_reels(reels, viewer_id=None):
    """Attach promotion metadata to reels backed by paid campaigns within the active window and record impressions."""
    reel_ids = [r.id for r in reels if getattr(r, "id", None)]
    if not reel_ids:
        return reels
    now = datetime.utcnow()
    campaigns = (
        db.session.query(AdCampaign)
        .filter(
            AdCampaign.post_id.in_(reel_ids),
            AdCampaign.status == "paid",
            AdCampaign.start_date <= now,
            AdCampaign.end_date >= now,
        )
        .all()
    )
    cmap = {c.post_id: c for c in campaigns}
    promoted_campaigns = []
    for reel in reels:
        camp = cmap.get(reel.id)
        if camp:
            setattr(reel, "is_promoted", True)
            setattr(reel, "promoted_label", "Promoted")
            setattr(reel, "promoted_order_id", camp.razorpay_order_id)
            promoted_campaigns.append(camp)
    if promoted_campaigns and viewer_id:
        record_impressions(promoted_campaigns, viewer_id)
    return reels


def get_trending_cached(limit=30):
    cached = current_app.redis_client.get("cache:trending_reels")
    if cached:
        try:
            raw_ids = json.loads(cached)
        except json.JSONDecodeError:
            raw_ids = []

        id_list = []
        for value in raw_ids:
            try:
                id_list.append(value if isinstance(value, uuid.UUID) else uuid.UUID(str(value)))
            except (ValueError, AttributeError, TypeError):
                # Skip any malformed ids in cache
                continue

        if id_list:
            reels = Reel.query.filter(Reel.id.in_(id_list)).all()
            order = {rid: idx for idx, rid in enumerate(id_list)}
            reels = sorted(reels, key=lambda r: order.get(r.id, len(order)))
            return reels[:limit]
    return compute_trending(limit)


def _clean_uuid_list(raw_ids):
    cleaned = []
    for val in raw_ids or []:
        if not val:
            continue
        try:
            cleaned.append(val if isinstance(val, uuid.UUID) else uuid.UUID(str(val)))
        except (ValueError, TypeError, AttributeError):
            continue
    return cleaned


def personalized_reels(user_id: str, limit=20, offset=0):
    user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))

    blocked = db.session.query(Block.target_id).filter(Block.user_id == user_uuid)
    blocked_by = db.session.query(Block.user_id).filter(Block.target_id == user_uuid)
    following = db.session.query(Follow.following_id).filter(Follow.follower_id == user_uuid)

    base = (
        db.session.query(Reel)
        .outerjoin(ReelInsight, ReelInsight.reel_id == Reel.id)
        .join(User, User.id == Reel.user_id)
        .filter(Reel.is_published.is_(True))
        .filter(~Reel.user_id.in_(blocked))
        .filter(~Reel.user_id.in_(blocked_by))
        .filter((User.is_private.is_(False)) | (Reel.user_id.in_(following)) | (Reel.user_id == user_uuid))
    )

    seen_key = f"user:{user_uuid}:seen_reels"
    raw_seen = current_app.redis_client.smembers(seen_key) if current_app else []
    seen_ids = _clean_uuid_list(raw_seen)

    base_opts = [selectinload(Reel.music), selectinload(Reel.stickers), selectinload(Reel.effects), selectinload(Reel.insights)]

    # Unseen first (new), most recent first
    unseen_q = base
    if seen_ids:
        unseen_q = unseen_q.filter(~Reel.id.in_(seen_ids))
    unseen_rows = (
        unseen_q.order_by(desc(Reel.created_at))
        .limit(max(limit + offset, limit))
        .options(*base_opts)
        .all()
    )

    remaining_needed = max(limit + offset - len(unseen_rows), 0)

    # Seen next, random order
    seen_rows = []
    if remaining_needed > 0 or offset > 0:
        if seen_ids:
            seen_rows = (
                base.filter(Reel.id.in_(seen_ids))
                .order_by(func.random())
                .limit(limit + offset + 10)
                .options(*base_opts)
                .all()
            )

    ordered = unseen_rows + seen_rows
    start = max(int(offset or 0), 0)
    end = start + limit
    result = ordered[start:end]
    annotate_promoted_reels(result, viewer_id=user_uuid)
    return result
