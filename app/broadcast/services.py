import uuid
from datetime import datetime
from typing import Sequence
from sqlalchemy import func
from app.extensions import db
from app.models import BroadcastChannel, ChannelSubscriber, BroadcastMessage, BroadcastOpen


class BroadcastError(Exception):
    pass


def _as_uuid(value, label="id"):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise BroadcastError(f"Invalid {label}") from exc


def create_channel(owner_id: str, name: str, description: str | None = None) -> BroadcastChannel:
    owner_uuid = _as_uuid(owner_id, "user id")
    channel = BroadcastChannel(name=name.strip(), description=description, created_by=owner_uuid)
    db.session.add(channel)
    db.session.flush()
    db.session.add(ChannelSubscriber(channel_id=channel.id, user_id=owner_uuid))
    db.session.commit()
    return channel


def subscribe(channel_id: str, user_id: str):
    channel_uuid = _as_uuid(channel_id, "channel id")
    user_uuid = _as_uuid(user_id, "user id")
    if ChannelSubscriber.query.filter_by(channel_id=channel_uuid, user_id=user_uuid).first():
        return
    db.session.add(ChannelSubscriber(channel_id=channel_uuid, user_id=user_uuid))
    db.session.commit()


def unsubscribe(channel_id: str, user_id: str):
    channel_uuid = _as_uuid(channel_id, "channel id")
    user_uuid = _as_uuid(user_id, "user id")
    sub = ChannelSubscriber.query.filter_by(channel_id=channel_uuid, user_id=user_uuid).first()
    if sub:
        db.session.delete(sub)
        db.session.commit()


def create_broadcast(channel_id: str, sender_id: str, content: str, scheduled_at: datetime | None = None) -> BroadcastMessage:
    channel_uuid = _as_uuid(channel_id, "channel id")
    sender_uuid = _as_uuid(sender_id, "user id")
    channel = BroadcastChannel.query.get(channel_uuid)
    if not channel:
        raise BroadcastError("Channel not found")
    if str(channel.created_by) != str(sender_uuid):
        raise BroadcastError("Only creator can broadcast")
    msg = BroadcastMessage(channel_id=channel_uuid, sender_id=sender_uuid, content=content.strip(), scheduled_at=scheduled_at)
    db.session.add(msg)
    db.session.commit()
    return msg


def mark_sent(message_id: str):
    msg_uuid = _as_uuid(message_id, "message id")
    msg = BroadcastMessage.query.get(msg_uuid)
    if not msg:
        return
    msg.sent_at = datetime.utcnow()
    db.session.commit()


def track_open(message_id: str, user_id: str):
    msg_uuid = _as_uuid(message_id, "message id")
    user_uuid = _as_uuid(user_id, "user id")
    if BroadcastOpen.query.filter_by(message_id=msg_uuid, user_id=user_uuid).first():
        return
    db.session.add(BroadcastOpen(message_id=msg_uuid, user_id=user_uuid))
    db.session.commit()


def channel_open_rate(channel_id: str) -> float:
    channel_uuid = _as_uuid(channel_id, "channel id")
    total_messages = BroadcastMessage.query.filter_by(channel_id=channel_uuid).count()
    if total_messages == 0:
        return 0.0
    opens = (
        db.session.query(BroadcastOpen)
        .join(BroadcastMessage, BroadcastOpen.message_id == BroadcastMessage.id)
        .filter(BroadcastMessage.channel_id == channel_uuid)
        .count()
    )
    return opens / total_messages


def list_channel_messages(channel_id: str, limit: int = 50):
    channel_uuid = _as_uuid(channel_id, "channel id")
    return BroadcastMessage.query.filter_by(channel_id=channel_uuid).order_by(BroadcastMessage.created_at.desc()).limit(limit).all()


def channel_subscribers(channel_id: str) -> Sequence[ChannelSubscriber]:
    channel_uuid = _as_uuid(channel_id, "channel id")
    return ChannelSubscriber.query.filter_by(channel_id=channel_uuid).all()


def list_user_channels(user_id: str) -> Sequence[BroadcastChannel]:
    user_uuid = _as_uuid(user_id, "user id")
    owned = BroadcastChannel.query.filter(BroadcastChannel.created_by == user_uuid)
    joined = (
        BroadcastChannel.query.join(ChannelSubscriber, ChannelSubscriber.channel_id == BroadcastChannel.id)
        .filter(ChannelSubscriber.user_id == user_uuid)
    )
    return owned.union(joined).all()


def list_all_channels(user_id: str):
    user_uuid = _as_uuid(user_id, "user id")

    # Subscriber counts per channel
    sub_counts = dict(
        db.session.query(ChannelSubscriber.channel_id, func.count())
        .group_by(ChannelSubscriber.channel_id)
        .all()
    )

    # Channels current user subscribed to
    user_subs = {
        row[0]
        for row in db.session.query(ChannelSubscriber.channel_id)
        .filter(ChannelSubscriber.user_id == user_uuid)
        .all()
    }

    channels = BroadcastChannel.query.all()
    results = []
    for c in channels:
        cid = c.id
        results.append(
            {
                "channel": c,
                "subscriber_count": sub_counts.get(cid, 0),
                "is_owner": str(c.created_by) == str(user_uuid),
                "is_subscribed": cid in user_subs,
            }
        )
    return results
