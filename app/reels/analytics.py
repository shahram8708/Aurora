import uuid
from sqlalchemy import func
from app.extensions import db
from app.models import ReelInsight


def _as_uuid(value):
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("Invalid reel id") from exc


def ensure_insight(reel_id):
    rid = _as_uuid(reel_id)
    insight = ReelInsight.query.filter_by(reel_id=rid).first()
    if not insight:
        insight = ReelInsight(reel_id=rid)
        db.session.add(insight)
        db.session.commit()
    return insight


def increment_view(reel_id):
    rid = _as_uuid(reel_id)
    db.session.query(ReelInsight).filter_by(reel_id=rid).update({ReelInsight.view_count: ReelInsight.view_count + 1})
    db.session.commit()


def increment_like(reel_id):
    rid = _as_uuid(reel_id)
    db.session.query(ReelInsight).filter_by(reel_id=rid).update({ReelInsight.like_count: ReelInsight.like_count + 1})
    db.session.commit()


def increment_comment(reel_id):
    rid = _as_uuid(reel_id)
    db.session.query(ReelInsight).filter_by(reel_id=rid).update({ReelInsight.comment_count: ReelInsight.comment_count + 1})
    db.session.commit()


def increment_share(reel_id):
    rid = _as_uuid(reel_id)
    # Ensure a row exists so the increment actually applies
    ensure_insight(rid)
    db.session.query(ReelInsight).filter_by(reel_id=rid).update({ReelInsight.share_count: ReelInsight.share_count + 1})
    db.session.commit()


def add_watch_time(reel_id, watch_seconds: float):
    rid = _as_uuid(reel_id)
    row = db.session.query(ReelInsight).filter_by(reel_id=rid)
    row.update({
        ReelInsight.watch_time: ReelInsight.watch_time + watch_seconds,
        # SQLite lacks GREATEST; use MAX to enforce a minimum of 1 view
        ReelInsight.view_count: func.max(ReelInsight.view_count, 1),
    })
    db.session.commit()
    insight = ReelInsight.query.filter_by(reel_id=rid).first()
    if insight and insight.view_count:
        insight.avg_watch_time = float(insight.watch_time) / float(insight.view_count)
        db.session.commit()
