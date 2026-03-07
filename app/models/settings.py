import uuid
from datetime import datetime, timedelta
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import UniqueConstraint
from app.extensions import db
from .user import TimestampMixin


class UserSetting(db.Model, TimestampMixin):
    __tablename__ = "user_settings"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    is_private = db.Column(db.Boolean, default=False, nullable=False)
    show_activity = db.Column(db.Boolean, default=True, nullable=False)
    story_visibility = db.Column(db.String(32), default="followers", nullable=False)
    dm_privacy = db.Column(db.String(32), default="followers", nullable=False)
    search_visibility = db.Column(db.Boolean, default=True, nullable=False)
    two_factor_enabled = db.Column(db.Boolean, default=False, nullable=False)
    language = db.Column(db.String(10), default="en", nullable=False)
    theme = db.Column(db.String(10), default="light", nullable=False)
    restricted_mode = db.Column(db.Boolean, default=False, nullable=False)
    screen_time_limit_minutes = db.Column(db.Integer, default=0, nullable=False)
    parent_account_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    linked_accounts = db.Column(db.JSON, nullable=True)


class DataExportJob(db.Model, TimestampMixin):
    __tablename__ = "data_export_jobs"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = db.Column(db.String(32), default="pending", nullable=False)
    storage_url = db.Column(db.String(512), nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    token = db.Column(db.String(255), unique=True, nullable=False)

    def mark_ready(self, url: str, ttl_hours: int):
        self.status = "ready"
        self.storage_url = url
        self.expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)


class DeviceSession(db.Model, TimestampMixin):
    __tablename__ = "device_sessions"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device = db.Column(db.String(120), nullable=True)
    ip_address = db.Column(db.String(64), nullable=True)
    last_active_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "device", name="uq_device_per_user"),)
