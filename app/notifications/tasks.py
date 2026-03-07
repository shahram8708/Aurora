from flask import current_app
from app.extensions import celery, db
from app.email.email_service import send_email
import uuid
from app.models import Notification, DeviceToken, User
from .notification_service import serialize_notification, send_push_to_tokens


@celery.task(name="notifications.send_email")
def send_notification_email(notification_id: int):
    notif = Notification.query.get(notification_id)
    if not notif:
        return
    user = getattr(notif, "recipient", None)
    if not user:
        return
    template_map = {
        "dm": "social/dm_notification",
        "message_request": "social/dm_notification",
        "group_added": "social/dm_notification",
        "follow": "social/new_follow",
        "follow_request": "social/new_follow",
        "follow_approved": "social/new_follow",
        "like_post": "social/new_like",
        "like_reel": "social/new_like",
        "like_comment": "social/new_like",
        "comment_post": "social/new_comment",
        "reply_comment": "social/new_comment",
        "mention_post": "social/mention",
        "mention_comment": "social/mention",
        "tag_post": "social/mention",
        "tag_story": "social/mention",
        "story_reply": "social/new_comment",
        "live_started": "social/live_reminder",
        "live_reminder": "social/live_reminder",
        "payment_success": "commerce/payment_success",
        "payment_failed": "commerce/payment_failed",
        "order_confirmed": "commerce/order_confirmed",
        "shipment_sent": "commerce/shipment_sent",
        "delivery_completed": "commerce/delivery_completed",
        "refund_processed": "commerce/refund_processed",
        "login_new_device": "security/login_new_device",
        "password_changed": "security/password_changed",
        "account_suspended": "security/account_suspended",
        "account_restored": "security/account_restored",
        "report_resolved": "security/report_resolved",
        "copyright_strike": "security/copyright_strike",
    }
    template_name = template_map.get(notif.type, "social/new_comment")
    subject_map = {
        "dm": "New direct message",
        "message_request": "New message request",
        "group_added": "Added to a group",
        "follow": "New follower",
        "follow_request": "Follow request",
        "follow_approved": "Follow request accepted",
        "like_post": "New like",
        "like_reel": "New reel like",
        "like_comment": "New comment like",
        "comment_post": "New comment",
        "reply_comment": "New reply",
        "mention_post": "You were mentioned",
        "mention_comment": "You were mentioned",
        "tag_post": "You were tagged",
        "tag_story": "You were tagged",
        "story_reply": "New story reply",
        "live_started": "Live started",
        "live_reminder": "Live event reminder",
        "payment_success": "Payment successful",
        "payment_failed": "Payment failed",
        "order_confirmed": "Order confirmed",
        "shipment_sent": "Shipment sent",
        "delivery_completed": "Delivery delivered",
        "refund_processed": "Refund processed",
        "login_new_device": "Login from new device",
        "password_changed": "Password changed",
        "account_suspended": "Account suspended",
        "account_restored": "Account restored",
        "report_resolved": "Report resolved",
        "copyright_strike": "Copyright notice",
    }
    actor_id = notif.actor_id
    actor = None
    if actor_id:
        actor_uuid = actor_id if isinstance(actor_id, uuid.UUID) else uuid.UUID(str(actor_id))
        actor = User.query.get(actor_uuid)
    cta_url = current_app.config.get("APP_BASE_URL", "https://example.com")
    send_email(
        template_name=template_name,
        recipient=user.email,
        subject=subject_map.get(notif.type, "New notification"),
        context={
            "user": {"name": user.name or user.username},
            "actor": actor.name if actor else None,
            "cta_url": cta_url,
            "reference_id": notif.reference_id,
            "meta": notif.meta or {},
            "unsubscribe_url": current_app.config.get("UNSUBSCRIBE_URL"),
        },
        priority="normal",
    )


@celery.task(name="notifications.send_push_batch")
def send_push_batch(notification_ids: list[int]):
    if not notification_ids:
        return
    notifs = Notification.query.filter(Notification.id.in_(notification_ids)).all()
    if not notifs:
        return
    for notif in notifs:
        tokens = [
            dt.token
            for dt in DeviceToken.query.filter_by(user_id=notif.recipient_id, is_active=True).all()
            if dt.token
        ]
        payload = serialize_notification(notif)
        send_push_to_tokens(tokens, payload)
        notif.is_read = notif.is_read  # no-op to keep session aware
    db.session.commit()
