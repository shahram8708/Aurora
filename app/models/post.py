import uuid
from datetime import datetime
from sqlalchemy import UniqueConstraint, Index, CheckConstraint, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.extensions import db


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Location(db.Model, TimestampMixin):
    __tablename__ = "locations"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, index=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)


class Post(db.Model, TimestampMixin):
    __tablename__ = "posts"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    caption = db.Column(db.Text, nullable=True)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    is_pinned = db.Column(db.Boolean, default=False, nullable=False)
    hide_like_count = db.Column(db.Boolean, default=False, nullable=False)
    branded_content_tag = db.Column(db.String(255), nullable=True)
    spam_score = db.Column(db.Float, nullable=False, default=0.0)
    is_sensitive = db.Column(db.Boolean, nullable=False, default=False)
    moderation_result = db.Column(db.JSON, nullable=True)

    user = db.relationship("User", backref=db.backref("posts", lazy="dynamic"))
    location = db.relationship("Location")
    media = db.relationship("PostMedia", backref="post", cascade="all, delete-orphan", order_by="PostMedia.order_index")
    hashtags = db.relationship("Hashtag", secondary="post_hashtags", back_populates="posts")
    tags = db.relationship("PostTag", backref="post", cascade="all, delete-orphan")
    likes = db.relationship("Like", backref="post", cascade="all, delete-orphan")
    comments = db.relationship("Comment", backref="post", cascade="all, delete-orphan")
    saves = db.relationship("Save", backref="post", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_posts_user_created", "user_id", "created_at"),
        Index("ix_posts_archived", "is_archived"),
        Index("ix_posts_spam", "spam_score"),
    )


class PostMedia(db.Model, TimestampMixin):
    __tablename__ = "post_media"

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(UUID(as_uuid=True), db.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    media_type = db.Column(db.String(10), nullable=False)  # image or video
    media_url = db.Column(db.String(512), nullable=False)
    thumbnail_url = db.Column(db.String(512), nullable=True)
    alt_text = db.Column(db.String(255), nullable=True)
    order_index = db.Column(db.Integer, default=0, nullable=False)
    width = db.Column(db.Integer, nullable=True)
    height = db.Column(db.Integer, nullable=True)
    duration_seconds = db.Column(db.Float, nullable=True)

    __table_args__ = (
        Index("ix_post_media_post_order", "post_id", "order_index"),
    )


class Hashtag(db.Model, TimestampMixin):
    __tablename__ = "hashtags"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    posts = db.relationship("Post", secondary="post_hashtags", back_populates="hashtags")


class PostHashtag(db.Model):
    __tablename__ = "post_hashtags"

    post_id = db.Column(UUID(as_uuid=True), db.ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True)
    hashtag_id = db.Column(db.Integer, db.ForeignKey("hashtags.id", ondelete="CASCADE"), primary_key=True)
    __table_args__ = (Index("ix_post_hashtag_post", "post_id"), Index("ix_post_hashtag_hashtag", "hashtag_id"))


class PostTag(db.Model, TimestampMixin):
    __tablename__ = "post_tags"

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(UUID(as_uuid=True), db.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    tagged_user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    position_x = db.Column(db.Float, nullable=True)
    position_y = db.Column(db.Float, nullable=True)

    __table_args__ = (UniqueConstraint("post_id", "tagged_user_id", name="uq_post_tag_user"),)


class Like(db.Model, TimestampMixin):
    __tablename__ = "likes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    post_id = db.Column(UUID(as_uuid=True), db.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)

    user = db.relationship("User")

    __table_args__ = (
        UniqueConstraint("user_id", "post_id", name="uq_like"),
        Index("ix_like_post", "post_id"),
    )


class Comment(db.Model, TimestampMixin):
    __tablename__ = "comments"

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(UUID(as_uuid=True), db.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_comment_id = db.Column(db.Integer, db.ForeignKey("comments.id", ondelete="CASCADE"), nullable=True, index=True)
    content = db.Column(db.Text, nullable=False)
    is_pinned = db.Column(db.Boolean, default=False, nullable=False)

    replies = db.relationship("Comment", cascade="all, delete-orphan")
    user = db.relationship("User")

    __table_args__ = (
        Index("ix_comment_post_parent", "post_id", "parent_comment_id"),
        CheckConstraint("length(content) > 0", name="ck_comment_content_len"),
    )


class Save(db.Model, TimestampMixin):
    __tablename__ = "saves"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    post_id = db.Column(UUID(as_uuid=True), db.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "post_id", name="uq_save"),
        Index("ix_save_user", "user_id"),
    )


class Follow(db.Model, TimestampMixin):
    __tablename__ = "follows"

    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    following_id = db.Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    __table_args__ = (
        UniqueConstraint("follower_id", "following_id", name="uq_follow"),
        Index("ix_follow_follower", "follower_id"),
        Index("ix_follow_following", "following_id"),
    )


class StoryShare(db.Model, TimestampMixin):
    __tablename__ = "story_shares"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    post_id = db.Column(UUID(as_uuid=True), db.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)

    __table_args__ = (Index("ix_story_share_user", "user_id"),)


class DirectShare(db.Model, TimestampMixin):
    __tablename__ = "direct_shares"

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    receiver_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    post_id = db.Column(UUID(as_uuid=True), db.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)

    __table_args__ = (
        Index("ix_direct_share_sender", "sender_id"),
        Index("ix_direct_share_receiver", "receiver_id"),
    )
