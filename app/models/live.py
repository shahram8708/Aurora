import uuid
from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import UniqueConstraint, Index
from app.extensions import db
from .user import TimestampMixin


class LiveSession(db.Model, TimestampMixin):
    __tablename__ = "live_sessions"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    host_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(140), nullable=False)
    description = db.Column(db.Text, nullable=True)
    scheduled_at = db.Column(db.DateTime, nullable=True, index=True)
    started_at = db.Column(db.DateTime, nullable=True)
    ended_at = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=False, nullable=False, index=True)
    replay_url = db.Column(db.String(512), nullable=True)
    stream_key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    slow_mode_seconds = db.Column(db.Integer, default=0, nullable=False)
    comments_enabled = db.Column(db.Boolean, default=True, nullable=False)

    __table_args__ = (
        Index("ix_live_active_host", "host_id", "is_active"),
        Index("ix_live_sched", "scheduled_at"),
    )


class LiveParticipant(db.Model):
    __tablename__ = "live_participants"

    session_id = db.Column(UUID(as_uuid=True), db.ForeignKey("live_sessions.id", ondelete="CASCADE"), primary_key=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role = db.Column(db.String(16), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_live_participant_role", "session_id", "role"),
    )


class LiveComment(db.Model):
    __tablename__ = "live_comments"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = db.Column(UUID(as_uuid=True), db.ForeignKey("live_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    message = db.Column(db.Text, nullable=False)
    pinned = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_live_comment_session_time", "session_id", "created_at"),
    )


class LiveReaction(db.Model):
    __tablename__ = "live_reactions"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = db.Column(UUID(as_uuid=True), db.ForeignKey("live_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    reaction_type = db.Column(db.String(32), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_live_reaction_session_type", "session_id", "reaction_type"),
    )


class LiveBadgeTransaction(db.Model):
    __tablename__ = "live_badge_transactions"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = db.Column(UUID(as_uuid=True), db.ForeignKey("live_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(8), default="INR", nullable=False)
    razorpay_payment_id = db.Column(db.String(80), nullable=False)
    razorpay_order_id = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("razorpay_payment_id", name="uq_badge_payment"),
        Index("ix_badge_session_sender", "session_id", "sender_id"),
    )


class LiveModerationAction(db.Model):
    __tablename__ = "live_moderation_actions"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = db.Column(UUID(as_uuid=True), db.ForeignKey("live_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    target_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action = db.Column(db.String(32), nullable=False)  # mute, remove, block, pin
    reason = db.Column(db.String(255), nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_live_moderation_action", "session_id", "target_id", "action"),
    )
