import uuid
from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import UniqueConstraint, Index
from app.extensions import db
from .user import TimestampMixin


class Role(db.Model, TimestampMixin):
    __tablename__ = "roles"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(50), unique=True, nullable=False, index=True)
    description = db.Column(db.String(255), nullable=True)


class Permission(db.Model, TimestampMixin):
    __tablename__ = "permissions"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(80), unique=True, nullable=False, index=True)
    description = db.Column(db.String(255), nullable=True)


class RolePermission(db.Model, TimestampMixin):
    __tablename__ = "role_permissions"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role_id = db.Column(UUID(as_uuid=True), db.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    permission_id = db.Column(UUID(as_uuid=True), db.ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False)

    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)


class UserRole(db.Model, TimestampMixin):
    __tablename__ = "user_roles"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id = db.Column(UUID(as_uuid=True), db.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_role"),
        Index("ix_user_role", "user_id", "role_id"),
    )


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = db.Column(db.String(120), nullable=False)
    target_type = db.Column(db.String(120), nullable=False)
    target_id = db.Column(db.String(120), nullable=True)
    metadata_json = db.Column(db.JSON, nullable=True)
    ip_address = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class LoginSession(db.Model, TimestampMixin):
    __tablename__ = "login_sessions"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    ip_address = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    last_seen_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (Index("ix_login_session_user", "user_id", "is_active"),)


class EnforcementStrike(db.Model, TimestampMixin):
    __tablename__ = "enforcement_strikes"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    reason = db.Column(db.String(255), nullable=False)
    severity = db.Column(db.String(32), default="medium", nullable=False)
    expires_at = db.Column(db.DateTime, nullable=True)
    appealable = db.Column(db.Boolean, default=True, nullable=False)


class EnforcementAppeal(db.Model, TimestampMixin):
    __tablename__ = "enforcement_appeals"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strike_id = db.Column(UUID(as_uuid=True), db.ForeignKey("enforcement_strikes.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = db.Column(db.String(32), default="pending", nullable=False)
    notes = db.Column(db.Text, nullable=True)
