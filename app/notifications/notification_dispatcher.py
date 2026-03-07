from __future__ import annotations
from typing import Any
from app.notifications.notification_service import create_notification, NotificationError


def dispatch_notification(
    recipient_id: str,
    actor_id: str | None,
    ntype: str,
    reference_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    *,
    send_email: bool = False,
    send_push: bool = True,
    send_realtime: bool = True,
    priority: str = "normal",
    dedup_key: str | None = None,
    batch_key: str | None = None,
):
    """Single entry point for all notification triggers."""
    return create_notification(
        recipient_id=recipient_id,
        actor_id=actor_id,
        ntype=ntype,
        reference_id=reference_id,
        metadata=metadata,
        send_email=send_email,
        send_push=send_push,
        send_realtime=send_realtime,
        priority=priority,
        dedup_key=dedup_key,
        batch_key=batch_key,
    )
