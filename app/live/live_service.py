import uuid
from datetime import datetime
from typing import Optional
from flask import current_app
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models import (
    LiveSession,
    LiveParticipant,
    LiveComment,
    LiveReaction,
    LiveBadgeTransaction,
    LiveModerationAction,
    LiveEarning,
    CreatorWallet,
)


class LiveError(Exception):
    pass


def generate_stream_key() -> str:
    return uuid.uuid4().hex


def _as_uuid(value) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def schedule_live(host_id: str, title: str, description: str | None, scheduled_at: datetime | None) -> LiveSession:
    if scheduled_at and scheduled_at <= datetime.utcnow():
        raise LiveError("Cannot schedule in the past")
    host_uuid = _as_uuid(host_id)
    session = LiveSession(
        host_id=host_uuid,
        title=title,
        description=description,
        scheduled_at=scheduled_at,
        stream_key=generate_stream_key(),
        slow_mode_seconds=current_app.config.get("LIVE_SLOW_MODE_SECONDS", 0),
    )
    db.session.add(session)
    db.session.flush()
    add_participant(session.id, host_uuid, role="host")
    db.session.commit()
    return session


def start_session(session_id: str, host_id: str) -> LiveSession:
    session_uuid = _as_uuid(session_id)
    host_uuid = _as_uuid(host_id)
    session = LiveSession.query.filter_by(id=session_uuid, host_id=host_uuid).first()
    if not session:
        raise LiveError("Session not found")
    session.started_at = datetime.utcnow()
    session.is_active = True
    db.session.commit()
    return session


def end_session(session_id: str, host_id: str, replay_url: Optional[str] = None) -> LiveSession:
    session_uuid = _as_uuid(session_id)
    host_uuid = _as_uuid(host_id)
    session = LiveSession.query.filter_by(id=session_uuid, host_id=host_uuid).first()
    if not session:
        raise LiveError("Session not found")
    session.ended_at = datetime.utcnow()
    session.is_active = False
    if replay_url:
        session.replay_url = replay_url
    db.session.commit()
    return session


def add_participant(session_id: str, user_id: str, role: str = "viewer") -> LiveParticipant:
    participant = LiveParticipant(session_id=_as_uuid(session_id), user_id=_as_uuid(user_id), role=role)
    db.session.merge(participant)
    return participant


def remove_participant(session_id: str, user_id: str):
    LiveParticipant.query.filter_by(session_id=_as_uuid(session_id), user_id=_as_uuid(user_id)).delete()
    db.session.commit()


def add_comment(session_id: str, user_id: str, message: str) -> LiveComment:
    session = LiveSession.query.get(_as_uuid(session_id))
    if not session or not session.is_active:
        raise LiveError("Session inactive")
    if not session.comments_enabled:
        raise LiveError("Comments disabled")
    comment = LiveComment(session_id=session.id, user_id=_as_uuid(user_id), message=message)
    db.session.add(comment)
    db.session.commit()
    return comment


def add_reaction(session_id: str, user_id: str, reaction_type: str) -> LiveReaction:
    session = LiveSession.query.get(_as_uuid(session_id))
    if not session or not session.is_active:
        raise LiveError("Session inactive")
    reaction = LiveReaction(session_id=session.id, user_id=_as_uuid(user_id), reaction_type=reaction_type)
    db.session.add(reaction)
    db.session.commit()
    return reaction


def record_badge(session_id: str, sender_id: str, amount: int, razorpay_payment_id: str, razorpay_order_id: str) -> LiveBadgeTransaction:
    txn = LiveBadgeTransaction(
        session_id=_as_uuid(session_id),
        sender_id=_as_uuid(sender_id),
        amount=amount,
        razorpay_payment_id=razorpay_payment_id,
        razorpay_order_id=razorpay_order_id,
    )
    try:
        db.session.add(txn)
        db.session.flush()
        _update_live_earning(session_id, amount)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise LiveError("Duplicate payment")
    return txn


def _update_live_earning(session_id: str, amount: int):
    fee_rate = current_app.config.get("BADGE_PLATFORM_FEE", 0.1)
    platform_fee = int(amount * fee_rate)
    creator_take = amount - platform_fee
    session_uuid = _as_uuid(session_id)
    earning = LiveEarning.query.filter_by(session_id=session_uuid).first()
    if not earning:
        earning = LiveEarning(session_id=session_uuid)
        db.session.add(earning)
    earning.total_badges_amount += amount
    earning.platform_fee_amount += platform_fee
    earning.creator_earnings += creator_take
    wallet = CreatorWallet.query.filter_by(user_id=LiveSession.query.get(session_uuid).host_id).first()
    if not wallet:
        wallet = CreatorWallet(user_id=LiveSession.query.get(session_uuid).host_id)
        db.session.add(wallet)
    wallet.available_balance += creator_take
    wallet.lifetime_earnings += amount
    wallet.lifetime_platform_fees += platform_fee
    wallet.last_earning_at = datetime.utcnow()


def set_slow_mode(session_id: str, seconds: int):
    LiveSession.query.filter_by(id=_as_uuid(session_id)).update({"slow_mode_seconds": seconds})
    db.session.commit()


def toggle_comments(session_id: str, enabled: bool):
    LiveSession.query.filter_by(id=_as_uuid(session_id)).update({"comments_enabled": enabled})
    db.session.commit()


def pin_comment(comment_id: int, session_id: str, actor_id: str):
    session_uuid = _as_uuid(session_id)
    comment = LiveComment.query.filter_by(id=comment_id, session_id=session_uuid).first()
    if not comment:
        raise LiveError("Comment not found")
    LiveModerationAction.query.filter_by(session_id=session_uuid, target_id=comment.user_id, action="pin").delete()
    comment.pinned = True
    db.session.commit()


def moderate_user(session_id: str, actor_id: str, target_id: str, action: str, reason: str | None = None, expires_at: datetime | None = None):
    session_uuid = _as_uuid(session_id)
    actor_uuid = _as_uuid(actor_id)
    target_uuid = _as_uuid(target_id)

    if action == "unblock":
        LiveModerationAction.query.filter_by(session_id=session_uuid, target_id=target_uuid, action="block").delete()
        db.session.commit()
        return {"action": "unblock", "id": None, "target_id": str(target_uuid)}

    record = LiveModerationAction(
        session_id=session_uuid,
        actor_id=actor_uuid,
        target_id=target_uuid,
        action=action,
        reason=reason,
        expires_at=expires_at,
    )
    db.session.add(record)
    db.session.commit()
    if action in {"remove", "block"}:
        remove_participant(session_id, target_id)
    return {"action": record.action, "id": str(record.id), "target_id": str(record.target_id)}
