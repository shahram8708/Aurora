from __future__ import annotations
from app.notifications.notification_service import _prefs  # reuse central loader
from app.models import NotificationPreference


def get_preferences(user_id: str) -> NotificationPreference:
    return _prefs(user_id)


def allow_channel(prefs: NotificationPreference, ntype: str, channel: str) -> bool:
    if channel == "email":
        return _email_allowed(prefs, ntype)
    if channel == "push":
        return _push_allowed(prefs, ntype)
    if channel == "in_app":
        return bool(prefs.in_app_enabled)
    return False


def _email_allowed(prefs: NotificationPreference, ntype: str) -> bool:
    flag_map = {
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
    flag = flag_map.get(ntype)
    return bool(getattr(prefs, flag, False)) if flag else False


def _push_allowed(prefs: NotificationPreference, ntype: str) -> bool:
    if not prefs.push_enabled:
        return False
    if ntype in {
        "payment_success",
        "payment_failed",
        "order_confirmed",
        "shipment_sent",
        "delivery_completed",
        "refund_processed",
        "wishlist_price_drop",
    }:
        return bool(prefs.push_commerce)
    if ntype in {
        "login_new_device",
        "password_changed",
        "account_suspended",
        "account_restored",
        "report_resolved",
        "copyright_strike",
    }:
        return bool(prefs.push_security)
    return True
