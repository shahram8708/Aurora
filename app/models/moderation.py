import uuid
from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Index
from app.extensions import db
from .user import TimestampMixin


class ContentReport(db.Model, TimestampMixin):
    __tablename__ = "content_reports"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_type = db.Column(db.String(32), nullable=False)  # post, reel, message, comment
    content_id = db.Column(db.String(120), nullable=False)
    reporter_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = db.Column(db.String(32), default="pending", nullable=False, index=True)
    assigned_to = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reason = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    ai_result = db.Column(db.JSON, nullable=True)
    is_sensitive = db.Column(db.Boolean, default=False, nullable=False)

    __table_args__ = (Index("ix_content_report", "content_type", "status"),)


class UserReport(db.Model, TimestampMixin):
    __tablename__ = "user_reports"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reported_user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reporter_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = db.Column(db.String(32), default="pending", nullable=False)
    notes = db.Column(db.Text, nullable=True)
    assigned_to = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class CopyrightReport(db.Model, TimestampMixin):
    __tablename__ = "copyright_reports"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_id = db.Column(db.String(120), nullable=False)
    reporter_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = db.Column(db.String(32), default="pending", nullable=False)
    proof_url = db.Column(db.String(512), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    strikes = db.Column(db.Integer, default=0, nullable=False)
    repeat_offender = db.Column(db.Boolean, default=False, nullable=False)

    __table_args__ = (Index("ix_copyright_status", "status"),)
