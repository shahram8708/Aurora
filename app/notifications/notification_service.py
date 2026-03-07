import uuid
from datetime import datetime, timedelta
from typing import Iterable
import json
import requests
from flask import current_app
from app.extensions import db, socketio
from app.models import Notification, DeviceToken, NotificationPreference, ConversationParticipant, Message, Block, Mute
from app.messaging.redis_pubsub import channel_for_user, publish_event

NOTIFICATION_NAMESPACE = "/ws/notifications"
PUSH_BATCH_SIZE = 100
AGGREGATION_WINDOW = timedelta(minutes=10)


class NotificationError(Exception):
    pass


NOTIFICATION_EMAIL_FLAGS = {
    "dm": "email_dm",
    "message_request": "email_dm",
    "group_added": "email_dm",
    "follow": "email_follow",
    "follow_request": "email_follow",
    "follow_approved": "email_follow",
    "like_post": "email_like",
    "like_reel": "email_like",
    "like_comment": "email_like",
    "comment_post": "email_comment",
    "reply_comment": "email_comment",
    "mention_post": "email_mention",
    "mention_comment": "email_mention",
    "tag_post": "email_mention",
    "tag_story": "email_mention",
    "story_reply": "email_comment",
    "live_started": "email_live",
    "live_reminder": "email_live",
    "payment_success": "email_commerce",
    "payment_failed": "email_commerce",
    "order_confirmed": "email_commerce",
    "shipment_sent": "email_commerce",
    "delivery_completed": "email_commerce",
    "refund_processed": "email_commerce",
    "wishlist_price_drop": "email_marketing",
    "login_new_device": "email_security",
    "password_changed": "email_security",
    "account_suspended": "email_security",
    "account_restored": "email_security",
    "report_resolved": "email_security",
    "copyright_strike": "email_security",
}


def _to_uuid(value):
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _prefs(user_id: str | uuid.UUID) -> NotificationPreference:
    uid = _to_uuid(user_id)
    if not uid:
        raise NotificationError("Invalid user_id")
    prefs = NotificationPreference.query.filter_by(user_id=uid).first()
    if prefs:
        return prefs
    prefs = NotificationPreference(user_id=uid)
    db.session.add(prefs)
    db.session.commit()
    return prefs


def _is_blocked(actor_id: str | uuid.UUID | None, recipient_id: str | uuid.UUID) -> bool:
    actor_uuid = _to_uuid(actor_id)
    recipient_uuid = _to_uuid(recipient_id)
    if not actor_uuid or not recipient_uuid:
        return False
    return bool(
        Block.query.filter_by(user_id=recipient_uuid, target_id=actor_uuid).first()
        or Block.query.filter_by(user_id=actor_uuid, target_id=recipient_uuid).first()
    )


def _is_muted(actor_id: str | uuid.UUID | None, recipient_id: str | uuid.UUID) -> bool:
    actor_uuid = _to_uuid(actor_id)
    recipient_uuid = _to_uuid(recipient_id)
    if not actor_uuid or not recipient_uuid:
        return False
    return bool(Mute.query.filter_by(user_id=recipient_uuid, target_id=actor_uuid).first())


def _in_quiet_hours(prefs: NotificationPreference) -> bool:
    if prefs.quiet_hours_start is None or prefs.quiet_hours_end is None:
        return False
    now_hour = datetime.utcnow().hour
    start = prefs.quiet_hours_start
    end = prefs.quiet_hours_end
    if start == end:
        return False
    if start < end:
        return start <= now_hour < end
    return now_hour >= start or now_hour < end


def create_notification(
    recipient_id: str | uuid.UUID,
    actor_id: str | uuid.UUID | None,
    ntype: str,
    reference_id: str | None = None,
    metadata: dict | None = None,
    *,
    send_email: bool = False,
    send_push: bool = True,
    send_realtime: bool = True,
    priority: str = "normal",
    dedup_key: str | None = None,
    batch_key: str | None = None,
) -> Notification:
    recipient_uuid = _to_uuid(recipient_id)
    actor_uuid = _to_uuid(actor_id) if actor_id is not None else None
    if not recipient_uuid:
        raise NotificationError("Invalid recipient_id")

    if _is_blocked(actor_uuid, recipient_uuid) or _is_muted(actor_uuid, recipient_uuid):
        raise NotificationError("Muted or blocked")

    prefs = _prefs(recipient_uuid)
    if not prefs.in_app_enabled:
        raise NotificationError("In-app disabled")

    now = datetime.utcnow()
    dedup = dedup_key or (reference_id and f"{ntype}:{reference_id}")
    notif = None
    if dedup:
        window_start = now - AGGREGATION_WINDOW
        notif = (
            Notification.query.filter_by(recipient_id=recipient_uuid, dedup_key=dedup, type=ntype)
            .filter(Notification.created_at >= window_start)
            .order_by(Notification.created_at.desc())
            .first()
        )
        if notif:
            notif.aggregated_count = (notif.aggregated_count or 1) + 1
            meta = notif.meta or {}
            actor_ids = set(meta.get("actor_ids", []))
            if actor_uuid:
                actor_ids.add(str(actor_uuid))
            meta["actor_ids"] = list(actor_ids)
            meta["latest_at"] = now.isoformat()
            if metadata:
                meta.update(metadata)
            notif.meta = meta
            notif.delivered_at = None
    if not notif:
        notif = Notification(
            recipient_id=recipient_uuid,
            actor_id=actor_uuid,
            type=ntype,
            reference_id=reference_id,
            meta=metadata or {},
            dedup_key=dedup,
            batch_key=batch_key,
            priority=priority,
            aggregated_count=1,
        )
        db.session.add(notif)

    db.session.commit()

    if send_realtime:
        emit_realtime(notif)
    if send_push:
        queue_push_if_enabled(notif, prefs)
    if send_email:
        queue_email_if_enabled(notif, prefs)
    else:
        queue_email_if_enabled(notif, prefs, prefer_flag=True)
    try:
        current_app.logger.info(
            "notification_created",
            extra={
                "recipient_id": str(recipient_uuid),
                "actor_id": str(actor_uuid) if actor_uuid else None,
                "type": ntype,
                "id": notif.id,
            },
        )
    except Exception:
        pass
    return notif


def emit_realtime(notif: Notification):
    payload = serialize_notification(notif)
    payload["unread"] = unread_count(str(notif.recipient_id))
    room = channel_for_user(str(notif.recipient_id))
    socketio.emit("notification", payload, room=room, namespace=NOTIFICATION_NAMESPACE)
    publish_event(room, payload)


def serialize_notification(notif: Notification) -> dict:
    return {
        "id": notif.id,
        "recipient_id": str(notif.recipient_id),
        "actor_id": str(notif.actor_id) if notif.actor_id else None,
        "type": notif.type,
        "reference_id": notif.reference_id,
        "meta": notif.meta or {},
        "is_read": notif.is_read,
        "aggregated_count": notif.aggregated_count,
        "priority": notif.priority,
        "created_at": notif.created_at.isoformat(),
    }


def mark_read(notification_id: int, user_id: str | uuid.UUID):
    uid = _to_uuid(user_id)
    if not uid:
        raise NotificationError("Invalid user_id")
    notif = Notification.query.filter_by(id=notification_id, recipient_id=uid).first()
    if not notif:
        raise NotificationError("Not found")
    notif.is_read = True
    notif.delivered_at = datetime.utcnow()
    db.session.commit()
    return notif


def mark_all_read(user_id: str | uuid.UUID, notification_ids: Iterable[int] | None = None):
    uid = _to_uuid(user_id)
    if not uid:
        raise NotificationError("Invalid user_id")
    query = Notification.query.filter_by(recipient_id=uid, is_read=False)
    if notification_ids:
        query = query.filter(Notification.id.in_(notification_ids))
    query.update({Notification.is_read: True, Notification.delivered_at: datetime.utcnow()}, synchronize_session=False)
    db.session.commit()


def delete_notifications(user_id: str | uuid.UUID, notification_ids: Iterable[int] | None = None) -> int:
    uid = _to_uuid(user_id)
    if not uid:
        raise NotificationError("Invalid user_id")
    query = Notification.query.filter_by(recipient_id=uid)
    if notification_ids:
        query = query.filter(Notification.id.in_(notification_ids))
    deleted = query.delete(synchronize_session=False)
    db.session.commit()
    return deleted


def unread_count(user_id: str | uuid.UUID) -> int:
    uid = _to_uuid(user_id)
    if not uid:
        return 0
    return Notification.query.filter_by(recipient_id=uid, is_read=False).count()


def list_notifications(user_id: str | uuid.UUID, limit: int = 30, before: datetime | None = None):
    uid = _to_uuid(user_id)
    if not uid:
        return []
    query = Notification.query.filter_by(recipient_id=uid).order_by(Notification.created_at.desc())
    if before:
        query = query.filter(Notification.created_at < before)
    return query.limit(limit).all()


def register_device_token(user_id: str | uuid.UUID, token: str, platform: str, device_id: str | None = None):
    uid = _to_uuid(user_id)
    if not uid:
        raise NotificationError("Invalid user_id")
    existing = DeviceToken.query.filter_by(user_id=uid, token=token).first()
    now = datetime.utcnow()
    if existing:
        existing.is_active = True
        existing.platform = platform
        existing.device_id = device_id
        existing.last_used_at = now
        existing.last_active_at = now
    else:
        db.session.add(
            DeviceToken(user_id=uid, token=token, platform=platform, device_id=device_id, last_active_at=now)
        )
    db.session.commit()


def _flag_enabled(prefs: NotificationPreference, flag: str) -> bool:
    return bool(getattr(prefs, flag, False))


def queue_email_if_enabled(notif: Notification, prefs: NotificationPreference, prefer_flag: bool = False):
    if not prefs.in_app_enabled:
        return
    flag = NOTIFICATION_EMAIL_FLAGS.get(notif.type)
    if prefer_flag and flag and not _flag_enabled(prefs, flag):
        return
    if _in_quiet_hours(prefs):
        return
    from app.notifications.tasks import send_notification_email

    send_notification_email.delay(notif.id)


def queue_push_if_enabled(notif: Notification, prefs: NotificationPreference):
    if not prefs.push_enabled:
        return
    if _in_quiet_hours(prefs):
        return
    if notif.type in {"login_new_device", "password_changed", "account_suspended", "account_restored", "report_resolved", "copyright_strike"} and not prefs.push_security:
        return
    if notif.type in {"payment_success", "payment_failed", "order_confirmed", "shipment_sent", "delivery_completed", "refund_processed", "wishlist_price_drop"} and not prefs.push_commerce:
        return
    from app.notifications.tasks import send_push_batch

    send_push_batch.delay([notif.id])


def enqueue_push(user_id: str, message: str, ntype: str = "live_reminder", meta: dict | None = None):
    create_notification(
        recipient_id=user_id,
        actor_id=None,
        ntype=ntype,
        reference_id=None,
        metadata={"message": message, **(meta or {})},
        send_email=False,
        send_push=True,
        send_realtime=True,
    )


def send_push_to_tokens(tokens: list[str], body: dict):
    if not tokens:
        return
    server_key = current_app.config.get("FCM_SERVER_KEY")
    if not server_key:
        current_app.logger.warning("FCM_SERVER_KEY missing; skipping push")
        return
    headers = {
        "Authorization": f"key={server_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "registration_ids": tokens,
        "data": body,
        "priority": "high",
    }
    url = current_app.config.get("FCM_API_URL", "https://fcm.googleapis.com/fcm/send")
    try:
        resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=5)
        if resp.status_code >= 400:
            current_app.logger.warning("FCM push failed: %s %s", resp.status_code, resp.text)
    except Exception as exc:  # pylint: disable=broad-except
        current_app.logger.exception("FCM push error: %s", exc)


def notify_dm_message(msg: Message, sender_id: str):
    participants = ConversationParticipant.query.filter(ConversationParticipant.conversation_id == msg.conversation_id).all()
    for participant in participants:
        rid = str(participant.user_id)
        if rid == sender_id or participant.is_request:
            continue
        create_notification(
            recipient_id=rid,
            actor_id=sender_id,
            ntype="dm",
            reference_id=str(msg.id),
            metadata={"conversation_id": str(msg.conversation_id), "message_type": msg.message_type},
            dedup_key=f"dm:{msg.conversation_id}",
        )
