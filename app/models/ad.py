import uuid
from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Index
from app.extensions import db
from .user import TimestampMixin


class AdCampaign(db.Model, TimestampMixin):
    __tablename__ = "ad_campaigns"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    post_id = db.Column(UUID(as_uuid=True), db.ForeignKey("posts.id", ondelete="CASCADE"), nullable=True, index=True)
    name = db.Column(db.String(120), nullable=False)
    budget = db.Column(db.Integer, nullable=False)
    spent = db.Column(db.Integer, default=0, nullable=False)
    status = db.Column(db.String(32), default="draft", nullable=False)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    target_audience = db.Column(db.JSON, nullable=False)
    visibility_score_boost = db.Column(db.Float, default=0.0, nullable=False)
    razorpay_order_id = db.Column(db.String(80), nullable=True, unique=True)

    __table_args__ = (
        Index("ix_campaign_status", "status"),
        Index("ix_campaign_dates", "start_date", "end_date"),
    )


class AdPerformance(db.Model):
    __tablename__ = "ad_performance"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    campaign_id = db.Column(UUID(as_uuid=True), db.ForeignKey("ad_campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    impressions = db.Column(db.Integer, default=0, nullable=False)
    clicks = db.Column(db.Integer, default=0, nullable=False)
    spend = db.Column(db.Integer, default=0, nullable=False)
    revenue = db.Column(db.Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_ad_perf_campaign_date", "campaign_id", "date", unique=True),
    )
