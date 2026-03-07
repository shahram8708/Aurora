import uuid
from datetime import datetime
from sqlalchemy import UniqueConstraint, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.extensions import db


class Conversation(db.Model):
    __tablename__ = "conversations"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    is_group = db.Column(db.Boolean, default=False, nullable=False)
    title = db.Column(db.String(120), nullable=True)
    avatar_url = db.Column(db.String(512), nullable=True)
    theme = db.Column(db.String(40), nullable=False, default="default")
    created_by = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    last_message_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    participants = db.relationship(
        "ConversationParticipant",
        backref="conversation",
        cascade="all, delete-orphan",
    )
    messages = db.relationship(
        "Message",
        backref="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )

    __table_args__ = (
        Index("ix_conversation_updated", "updated_at"),
        Index("ix_conversation_last_msg", "last_message_at"),
    )


class ConversationParticipant(db.Model):
    __tablename__ = "conversation_participants"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(UUID(as_uuid=True), db.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = db.Column(db.String(20), default="member", nullable=False)
    is_muted = db.Column(db.Boolean, default=False, nullable=False)
    is_request = db.Column(db.Boolean, default=False, nullable=False)
    last_read_at = db.Column(db.DateTime, nullable=True)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    theme = db.Column(db.String(40), nullable=True)

    user = db.relationship("User")

    __table_args__ = (
        UniqueConstraint("conversation_id", "user_id", name="uq_conversation_participant"),
        Index("ix_conv_part_user", "user_id"),
        Index("ix_conv_part_conversation", "conversation_id"),
    )


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = db.Column(UUID(as_uuid=True), db.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    message_type = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=True)
    media_url = db.Column(db.String(512), nullable=True)
    media_mime_type = db.Column(db.String(100), nullable=True)
    media_size_bytes = db.Column(db.Integer, nullable=True)
    duration_seconds = db.Column(db.Float, nullable=True)
    thumbnail_url = db.Column(db.String(512), nullable=True)
    reply_to_id = db.Column(UUID(as_uuid=True), db.ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    is_vanish = db.Column(db.Boolean, default=False, nullable=False)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    gif_provider = db.Column(db.String(50), nullable=True)
    gif_id = db.Column(db.String(120), nullable=True)
    autoplay = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    sender = db.relationship("User")
    reply_to = db.relationship("Message", remote_side=[id])
    reactions = db.relationship("MessageReaction", backref="message", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_message_conversation_created", "conversation_id", "created_at"),
        Index("ix_message_sender_created", "sender_id", "created_at"),
        CheckConstraint("message_type <> ''", name="ck_message_type_not_empty"),
    )


class MessageReaction(db.Model):
    __tablename__ = "message_reactions"

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(UUID(as_uuid=True), db.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reaction_type = db.Column(db.String(30), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User")

    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_message_reaction"),
        Index("ix_message_reaction_message", "message_id"),
        Index("ix_message_reaction_user", "user_id"),
    )


class MessageReport(db.Model):
    __tablename__ = "message_reports"

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(UUID(as_uuid=True), db.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    reported_by = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    reason = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    reporter = db.relationship("User", foreign_keys=[reported_by])
    __table_args__ = (
        UniqueConstraint("message_id", "reported_by", name="uq_message_report"),
    )
