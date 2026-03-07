import uuid
from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Index, UniqueConstraint
from app.extensions import db
from .user import TimestampMixin


class AudienceDemographic(db.Model, TimestampMixin):
    __tablename__ = "audience_demographics"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    age_group = db.Column(db.String(20), nullable=False)
    gender = db.Column(db.String(20), nullable=False)
    country = db.Column(db.String(80), nullable=False)
    city = db.Column(db.String(120), nullable=True)
    count = db.Column(db.Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("creator_id", "age_group", "gender", "country", "city", name="uq_demo_bucket"),
        Index("ix_demo_creator_age", "creator_id", "age_group"),
    )


class RevenueAggregate(db.Model, TimestampMixin):
    __tablename__ = "revenue_aggregates"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    earnings = db.Column(db.Integer, default=0, nullable=False)
    source = db.Column(db.String(32), nullable=False)  # ads, badges, subscriptions, affiliate
    platform_fees = db.Column(db.Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("creator_id", "date", "source", name="uq_revenue_daily"),
        Index("ix_revenue_source", "source"),
    )
