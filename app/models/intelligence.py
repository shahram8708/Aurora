import uuid
from datetime import datetime
from sqlalchemy import Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.extensions import db


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class InterestGraph(db.Model, TimestampMixin):
    __tablename__ = "interest_graph"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    tag_id = db.Column(db.Integer, db.ForeignKey("hashtags.id", ondelete="CASCADE"), nullable=False, index=True)
    weight = db.Column(db.Float, nullable=False, default=0.1)

    __table_args__ = (
        UniqueConstraint("user_id", "tag_id", name="uq_interest_user_tag"),
        Index("ix_interest_weight", "weight"),
    )


class ModerationEvent(db.Model, TimestampMixin):
    __tablename__ = "moderation_events"

    id = db.Column(db.Integer, primary_key=True)
    content_type = db.Column(db.String(30), nullable=False)
    content_id = db.Column(UUID(as_uuid=True), nullable=False, index=True)
    provider = db.Column(db.String(50), nullable=False, default="external")
    result = db.Column(db.JSON, nullable=True)
    score = db.Column(db.Float, nullable=True)
    action = db.Column(db.String(30), nullable=False, default="allow")
    is_flagged = db.Column(db.Boolean, nullable=False, default=False)
    reason = db.Column(db.String(255), nullable=True)

    __table_args__ = (
        Index("ix_mod_content", "content_type", "content_id"),
        Index("ix_mod_flag", "is_flagged"),
    )


class SuspiciousFollower(db.Model, TimestampMixin):
    __tablename__ = "suspicious_followers"

    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    following_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    suspicion_score = db.Column(db.Float, nullable=False, default=0.0)
    reason = db.Column(db.String(255), nullable=True)

    __table_args__ = (
        UniqueConstraint("follower_id", "following_id", name="uq_suspicious_follow"),
        Index("ix_suspicion_score", "suspicion_score"),
    )
