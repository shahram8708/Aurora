from datetime import datetime, timedelta
from sqlalchemy import func
from app.extensions import celery, db
from app.models import LiveBadgeTransaction, LiveEarning, LiveSession


@celery.task(name="app.monetization.tasks.recompute_live_earnings")
def recompute_live_earnings():
    since = datetime.utcnow() - timedelta(days=7)
    rows = (
        db.session.query(
            LiveBadgeTransaction.session_id,
            func.coalesce(func.sum(LiveBadgeTransaction.amount), 0).label("total"),
        )
        .filter(LiveBadgeTransaction.created_at >= since)
        .group_by(LiveBadgeTransaction.session_id)
        .all()
    )
    for row in rows:
        session = LiveSession.query.get(row.session_id)
        if not session:
            continue
        total = int(row.total)
        fee_rate = 0.1
        platform_fee = int(total * fee_rate)
        creator_take = total - platform_fee
        earning = LiveEarning.query.filter_by(session_id=row.session_id).first()
        if not earning:
            earning = LiveEarning(session_id=row.session_id)
            db.session.add(earning)
        earning.total_badges_amount = total
        earning.platform_fee_amount = platform_fee
        earning.creator_earnings = creator_take
    db.session.commit()
