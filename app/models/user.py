import uuid
from datetime import datetime, timedelta
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import UniqueConstraint, Index
from app.extensions import db


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class User(db.Model, TimestampMixin):
    __tablename__ = "users"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = db.Column(db.String(50), unique=True, index=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, index=True, nullable=False)
    phone = db.Column(db.String(20), unique=True, index=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    profile_photo_url = db.Column(db.String(512), nullable=True)
    bio = db.Column(db.Text, nullable=True)
    gender = db.Column(db.String(30), nullable=True)
    is_private = db.Column(db.Boolean, default=False, nullable=False)
    is_professional = db.Column(db.Boolean, default=False, nullable=False)
    category = db.Column(db.String(80), nullable=True)
    contact_email = db.Column(db.String(255), nullable=True)
    contact_phone = db.Column(db.String(20), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    terms_accepted_at = db.Column(db.DateTime, nullable=False)
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    phone_verified = db.Column(db.Boolean, default=False, nullable=False)
    failed_attempts = db.Column(db.Integer, default=0, nullable=False)
    last_failed_at = db.Column(db.DateTime, nullable=True)
    locked_until = db.Column(db.DateTime, nullable=True)
    follower_count = db.Column(db.Integer, default=0, nullable=False)
    following_count = db.Column(db.Integer, default=0, nullable=False)
    blur_sensitive = db.Column(db.Boolean, default=True, nullable=False)

    bio_links = db.relationship("BioLink", backref="user", cascade="all, delete-orphan")

    @property
    def is_authenticated(self) -> bool:
        return True

    def is_locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > datetime.utcnow())

    def register_failure(self, lock_threshold: int = 5, lock_minutes: int = 15):
        self.failed_attempts += 1
        self.last_failed_at = datetime.utcnow()
        if self.failed_attempts >= lock_threshold:
            self.locked_until = datetime.utcnow() + timedelta(minutes=lock_minutes)

    def reset_failures(self):
        self.failed_attempts = 0
        self.locked_until = None
        self.last_failed_at = None


class BioLink(db.Model, TimestampMixin):
    __tablename__ = "bio_links"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    label = db.Column(db.String(50), nullable=False)
    url = db.Column(db.String(255), nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "url", name="uq_user_bio_url"),)


class CloseFriend(db.Model, TimestampMixin):
    __tablename__ = "close_friends"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    target_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "target_id", name="uq_close_friend"),)


class Block(db.Model, TimestampMixin):
    __tablename__ = "blocks"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    target_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "target_id", name="uq_block"),)


class Restrict(db.Model, TimestampMixin):
    __tablename__ = "restricts"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    target_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "target_id", name="uq_restrict"),)


class Mute(db.Model, TimestampMixin):
    __tablename__ = "mutes"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    target_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "target_id", name="uq_mute"),)


class OAuthAccount(db.Model, TimestampMixin):
    __tablename__ = "oauth_accounts"
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(50), nullable=False)
    provider_account_id = db.Column(db.String(255), nullable=False)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    __table_args__ = (
        UniqueConstraint("provider", "provider_account_id", name="uq_provider_account"),
        Index("ix_oauth_user_provider", "user_id", "provider"),
    )


class PasswordResetToken(db.Model, TimestampMixin):
    __tablename__ = "password_reset_tokens"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token = db.Column(db.String(255), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False, nullable=False)


class EmailVerificationToken(db.Model, TimestampMixin):
    __tablename__ = "email_verification_tokens"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token = db.Column(db.String(255), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False, nullable=False)


class FollowRequest(db.Model, TimestampMixin):
    __tablename__ = "follow_requests"

    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    target_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False)

    requester = db.relationship("User", foreign_keys=[requester_id])
    target = db.relationship("User", foreign_keys=[target_id])

    __table_args__ = (
        UniqueConstraint("requester_id", "target_id", name="uq_follow_request"),
        Index("ix_follow_request_target", "target_id"),
        Index("ix_follow_request_requester", "requester_id"),
    )
