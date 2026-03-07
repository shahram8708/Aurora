import uuid
from datetime import datetime
from sqlalchemy import UniqueConstraint, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.extensions import db


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Story(db.Model, TimestampMixin):
    __tablename__ = "stories"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    media_url = db.Column(db.String(512), nullable=True)
    thumbnail_url = db.Column(db.String(512), nullable=True)
    text_content = db.Column(db.Text, nullable=True)
    story_type = db.Column(db.String(20), nullable=False)  # photo, video, text
    is_close_friends = db.Column(db.Boolean, nullable=False, default=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    drawing_json = db.Column(db.JSON, nullable=True)
    background_music_id = db.Column(db.Integer, db.ForeignKey("reel_music.id", ondelete="SET NULL"), nullable=True)

    music = db.relationship("ReelMusic")
    user = db.relationship("User", backref=db.backref("stories", lazy="dynamic"))
    stickers = db.relationship("StorySticker", backref="story", cascade="all, delete-orphan")
    insights = db.relationship("StoryInsight", backref="story", cascade="all, delete-orphan", uselist=False)
    replies = db.relationship("StoryReply", backref="story", cascade="all, delete-orphan")
    likes = db.relationship("StoryLike", backref="story", cascade="all, delete-orphan")
    views = db.relationship("StoryView", backref="story", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_story_user_created", "user_id", "created_at"),
        Index("ix_story_expires", "expires_at"),
    )


class StorySticker(db.Model, TimestampMixin):
    __tablename__ = "story_stickers"

    id = db.Column(db.Integer, primary_key=True)
    story_id = db.Column(UUID(as_uuid=True), db.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True)
    type = db.Column(db.String(50), nullable=False)
    metadata_json = db.Column(db.JSON, nullable=True)


class StoryHighlight(db.Model, TimestampMixin):
    __tablename__ = "story_highlights"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(80), nullable=False)
    cover_image = db.Column(db.String(512), nullable=True)

    items = db.relationship("StoryHighlightItem", backref="highlight", cascade="all, delete-orphan")


class StoryHighlightItem(db.Model, TimestampMixin):
    __tablename__ = "story_highlight_items"

    id = db.Column(db.Integer, primary_key=True)
    highlight_id = db.Column(db.Integer, db.ForeignKey("story_highlights.id", ondelete="CASCADE"), nullable=False)
    story_id = db.Column(UUID(as_uuid=True), db.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False)

    story = db.relationship("Story", backref=db.backref("highlight_items", cascade="all, delete-orphan"))

    __table_args__ = (UniqueConstraint("highlight_id", "story_id", name="uq_highlight_story"),)


class StoryInsight(db.Model, TimestampMixin):
    __tablename__ = "story_insights"

    story_id = db.Column(UUID(as_uuid=True), db.ForeignKey("stories.id", ondelete="CASCADE"), primary_key=True)
    view_count = db.Column(db.BigInteger, nullable=False, default=0)
    replies_count = db.Column(db.BigInteger, nullable=False, default=0)

    __table_args__ = (Index("ix_story_insight_views", "view_count"),)


class StoryReply(db.Model, TimestampMixin):
    __tablename__ = "story_replies"

    id = db.Column(db.Integer, primary_key=True)
    story_id = db.Column(UUID(as_uuid=True), db.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)

    user = db.relationship("User")

    __table_args__ = (
        Index("ix_story_reply_story", "story_id"),
        Index("ix_story_reply_user", "user_id"),
        CheckConstraint("length(content) > 0", name="ck_story_reply_len"),
    )


class StoryArchive(db.Model, TimestampMixin):
    __tablename__ = "story_archives"

    id = db.Column(UUID(as_uuid=True), primary_key=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    media_url = db.Column(db.String(512), nullable=True)
    text_content = db.Column(db.Text, nullable=True)
    story_type = db.Column(db.String(20), nullable=False)
    created_at_original = db.Column(db.DateTime, nullable=False)
    expired_at = db.Column(db.DateTime, nullable=False)


class StoryView(db.Model, TimestampMixin):
    __tablename__ = "story_views"

    id = db.Column(db.Integer, primary_key=True)
    story_id = db.Column(UUID(as_uuid=True), db.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False)
    viewer_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    user = db.relationship("User")

    __table_args__ = (
        UniqueConstraint("story_id", "viewer_id", name="uq_story_view_unique"),
        Index("ix_story_view_story", "story_id"),
    )


class StoryLike(db.Model, TimestampMixin):
    __tablename__ = "story_likes"

    id = db.Column(db.Integer, primary_key=True)
    story_id = db.Column(UUID(as_uuid=True), db.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    user = db.relationship("User")

    __table_args__ = (
        UniqueConstraint("story_id", "user_id", name="uq_story_like"),
        Index("ix_story_like_story", "story_id"),
        Index("ix_story_like_user", "user_id"),
    )
