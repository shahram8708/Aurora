import uuid
from datetime import datetime
from sqlalchemy import UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from app.extensions import db


class BroadcastChannel(db.Model):
    __tablename__ = "broadcast_channels"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_by = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("name", "created_by", name="uq_broadcast_name_owner"),
        Index("ix_broadcast_created", "created_at"),
    )


class ChannelSubscriber(db.Model):
    __tablename__ = "channel_subscribers"

    id = db.Column(db.Integer, primary_key=True)
    channel_id = db.Column(UUID(as_uuid=True), db.ForeignKey("broadcast_channels.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("channel_id", "user_id", name="uq_channel_subscriber"),
        Index("ix_channel_subscriber_channel", "channel_id"),
        Index("ix_channel_subscriber_user", "user_id"),
    )


class BroadcastMessage(db.Model):
    __tablename__ = "broadcast_messages"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id = db.Column(UUID(as_uuid=True), db.ForeignKey("broadcast_channels.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    scheduled_at = db.Column(db.DateTime, nullable=True)
    sent_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_broadcast_message_channel_created", "channel_id", "created_at"),
    )


class BroadcastOpen(db.Model):
    __tablename__ = "broadcast_opens"

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(UUID(as_uuid=True), db.ForeignKey("broadcast_messages.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    opened_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_broadcast_open"),
        Index("ix_broadcast_open_message", "message_id"),
        Index("ix_broadcast_open_user", "user_id"),
    )
