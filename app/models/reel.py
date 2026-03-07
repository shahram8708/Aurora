import uuid
from datetime import datetime
from sqlalchemy import Index, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.extensions import db


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ARFilter(db.Model, TimestampMixin):
    __tablename__ = "ar_filters"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    metadata_json = db.Column(db.JSON, nullable=True)


class ReelMusic(db.Model, TimestampMixin):
    __tablename__ = "reel_music"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    artist = db.Column(db.String(255), nullable=True)
    audio_url = db.Column(db.String(512), nullable=False)
    duration = db.Column(db.Float, nullable=False)
    license_type = db.Column(db.String(80), nullable=False, default="standard")
    usage_count = db.Column(db.Integer, nullable=False, default=0)


class Reel(db.Model, TimestampMixin):
    __tablename__ = "reels"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    caption = db.Column(db.Text, nullable=True)
    video_url = db.Column(db.String(512), nullable=False)
    thumbnail_url = db.Column(db.String(512), nullable=False)
    music_id = db.Column(db.Integer, db.ForeignKey("reel_music.id", ondelete="SET NULL"), nullable=True)
    speed_factor = db.Column(db.Float, nullable=False, default=1.0)
    is_remix = db.Column(db.Boolean, nullable=False, default=False)
    original_reel_id = db.Column(UUID(as_uuid=True), db.ForeignKey("reels.id", ondelete="SET NULL"), nullable=True)
    allow_download = db.Column(db.Boolean, nullable=False, default=True)
    monetization_enabled = db.Column(db.Boolean, nullable=False, default=False)
    scheduled_at = db.Column(db.DateTime, nullable=True)
    is_published = db.Column(db.Boolean, nullable=False, default=True)
    duration_seconds = db.Column(db.Float, nullable=False)
    width = db.Column(db.Integer, nullable=False)
    height = db.Column(db.Integer, nullable=False)
    text_overlays = db.Column(db.JSON, nullable=True)
    effects_metadata = db.Column(db.JSON, nullable=True)
    stickers_metadata = db.Column(db.JSON, nullable=True)
    voiceover_url = db.Column(db.String(512), nullable=True)
    voiceover_duration = db.Column(db.Float, nullable=True)
    mix_ratio = db.Column(db.Float, nullable=True)
    green_screen_background_url = db.Column(db.String(512), nullable=True)
    green_screen_subject_mask = db.Column(db.Boolean, nullable=False, default=False)
    countdown_seconds = db.Column(db.Integer, nullable=False, default=0)
    countdown_autostart = db.Column(db.Boolean, nullable=False, default=False)
    filter_id = db.Column(db.Integer, db.ForeignKey("ar_filters.id", ondelete="SET NULL"), nullable=True)
    spam_score = db.Column(db.Float, nullable=False, default=0.0)
    is_sensitive = db.Column(db.Boolean, nullable=False, default=False)
    moderation_result = db.Column(db.JSON, nullable=True)

    music = db.relationship("ReelMusic")
    filter = db.relationship("ARFilter")
    user = db.relationship("User", backref=db.backref("reels", lazy="dynamic"))
    original_reel = db.relationship("Reel", remote_side=[id])
    effects = db.relationship("ReelEffect", backref="reel", cascade="all, delete-orphan")
    stickers = db.relationship("ReelSticker", backref="reel", cascade="all, delete-orphan")
    insights = db.relationship("ReelInsight", backref="reel", cascade="all, delete-orphan", uselist=False)
    likes = db.relationship("ReelLike", backref="reel", cascade="all, delete-orphan")
    comments = db.relationship("ReelComment", backref="reel", cascade="all, delete-orphan")
    saves = db.relationship("ReelSave", backref="reel", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_reels_user_created", "user_id", "created_at"),
        Index("ix_reels_published", "is_published", "scheduled_at"),
        Index("ix_reels_spam", "spam_score"),
        CheckConstraint("countdown_seconds >= 0", name="ck_reel_countdown_positive"),
    )


class ReelEffect(db.Model, TimestampMixin):
    __tablename__ = "reel_effects"

    id = db.Column(db.Integer, primary_key=True)
    reel_id = db.Column(UUID(as_uuid=True), db.ForeignKey("reels.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    metadata_json = db.Column(db.JSON, nullable=True)


class ReelSticker(db.Model, TimestampMixin):
    __tablename__ = "reel_stickers"

    id = db.Column(db.Integer, primary_key=True)
    reel_id = db.Column(UUID(as_uuid=True), db.ForeignKey("reels.id", ondelete="CASCADE"), nullable=False, index=True)
    type = db.Column(db.String(50), nullable=False)
    metadata_json = db.Column(db.JSON, nullable=True)


class ReelInsight(db.Model, TimestampMixin):
    __tablename__ = "reel_insights"

    reel_id = db.Column(UUID(as_uuid=True), db.ForeignKey("reels.id", ondelete="CASCADE"), primary_key=True)
    view_count = db.Column(db.BigInteger, nullable=False, default=0)
    like_count = db.Column(db.BigInteger, nullable=False, default=0)
    comment_count = db.Column(db.BigInteger, nullable=False, default=0)
    share_count = db.Column(db.BigInteger, nullable=False, default=0)
    watch_time = db.Column(db.BigInteger, nullable=False, default=0)
    avg_watch_time = db.Column(db.Float, nullable=False, default=0.0)

    __table_args__ = (
        Index("ix_reel_insights_views", "view_count"),
        Index("ix_reel_insights_score", "view_count", "like_count", "share_count"),
        UniqueConstraint("reel_id", name="uq_reel_insight"),
    )


class ReelLike(db.Model, TimestampMixin):
    __tablename__ = "reel_likes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reel_id = db.Column(UUID(as_uuid=True), db.ForeignKey("reels.id", ondelete="CASCADE"), nullable=False, index=True)

    user = db.relationship("User")

    __table_args__ = (
        UniqueConstraint("user_id", "reel_id", name="uq_reel_like"),
        Index("ix_reel_like_user", "user_id"),
    )


class ReelComment(db.Model, TimestampMixin):
    __tablename__ = "reel_comments"

    id = db.Column(db.Integer, primary_key=True)
    reel_id = db.Column(UUID(as_uuid=True), db.ForeignKey("reels.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)

    user = db.relationship("User")

    __table_args__ = (
        Index("ix_reel_comment_reel_created", "reel_id", "created_at"),
        CheckConstraint("length(content) > 0", name="ck_reel_comment_content_len"),
    )


class ReelSave(db.Model, TimestampMixin):
    __tablename__ = "reel_saves"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reel_id = db.Column(UUID(as_uuid=True), db.ForeignKey("reels.id", ondelete="CASCADE"), nullable=False, index=True)

    user = db.relationship("User")

    __table_args__ = (
        UniqueConstraint("user_id", "reel_id", name="uq_reel_save"),
        Index("ix_reel_save_user", "user_id"),
    )
