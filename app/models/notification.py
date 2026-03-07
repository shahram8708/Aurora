import secrets
from datetime import datetime
from sqlalchemy import UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from app.extensions import db


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    type = db.Column(db.String(30), nullable=False)
    reference_id = db.Column(db.String(120), nullable=True)
    dedup_key = db.Column(db.String(120), nullable=True)
    batch_key = db.Column(db.String(120), nullable=True)
    aggregated_count = db.Column(db.Integer, default=1, nullable=False)
    priority = db.Column(db.String(10), default="normal", nullable=False)
    meta = db.Column(db.JSON, nullable=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    delivered_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_notification_recipient_created", "recipient_id", "created_at"),
        Index("ix_notification_read", "recipient_id", "is_read"),
        Index("ix_notification_dedup", "recipient_id", "dedup_key"),
        Index("ix_notification_batch", "recipient_id", "batch_key", "type"),
    )


class DeviceToken(db.Model):
    __tablename__ = "device_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token = db.Column(db.String(255), nullable=False)
    platform = db.Column(db.String(20), nullable=False)
    device_id = db.Column(db.String(120), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_used_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_active_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "token", name="uq_device_token_user"),
        Index("ix_device_token_active", "user_id", "is_active"),
    )


class NotificationPreference(db.Model):
    __tablename__ = "notification_preferences"

    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    email_dm = db.Column(db.Boolean, default=True, nullable=False)
    email_follow = db.Column(db.Boolean, default=True, nullable=False)
    email_like = db.Column(db.Boolean, default=True, nullable=False)
    email_comment = db.Column(db.Boolean, default=True, nullable=False)
    email_mention = db.Column(db.Boolean, default=True, nullable=False)
    email_live = db.Column(db.Boolean, default=True, nullable=False)
    email_marketing = db.Column(db.Boolean, default=False, nullable=False)
    email_security = db.Column(db.Boolean, default=True, nullable=False)
    email_commerce = db.Column(db.Boolean, default=True, nullable=False)
    push_enabled = db.Column(db.Boolean, default=True, nullable=False)
    push_security = db.Column(db.Boolean, default=True, nullable=False)
    push_commerce = db.Column(db.Boolean, default=True, nullable=False)
    in_app_enabled = db.Column(db.Boolean, default=True, nullable=False)
    quiet_hours_start = db.Column(db.SmallInteger, nullable=True)
    quiet_hours_end = db.Column(db.SmallInteger, nullable=True)
    unsubscribe_token = db.Column(db.String(64), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(32))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_notification_pref_user", "user_id"),
    )
