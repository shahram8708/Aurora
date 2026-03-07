import uuid
from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import UniqueConstraint, Index
from app.extensions import db
from .user import TimestampMixin


class BrandPartnership(db.Model, TimestampMixin):
    __tablename__ = "brand_partnerships"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    post_id = db.Column(UUID(as_uuid=True), db.ForeignKey("posts.id", ondelete="CASCADE"), nullable=True, index=True)
    creator_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    brand_name = db.Column(db.String(120), nullable=False)
    metadata_json = db.Column(db.JSON, nullable=True)
    status = db.Column(db.String(32), default="pending", nullable=False)
    agreed_amount = db.Column(db.Integer, nullable=True)
    is_paid_partnership = db.Column(db.Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("ix_brand_creator_status", "creator_id", "status"),
    )


class AffiliateLink(db.Model, TimestampMixin):
    __tablename__ = "affiliate_links"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_name = db.Column(db.String(140), nullable=False)
    url_slug = db.Column(db.String(80), unique=True, nullable=False)
    target_url = db.Column(db.String(512), nullable=False)
    commission_rate = db.Column(db.Float, default=0.1, nullable=False)
    click_count = db.Column(db.Integer, default=0, nullable=False)
    conversion_count = db.Column(db.Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_affiliate_creator", "creator_id"),
    )


class AffiliateConversion(db.Model, TimestampMixin):
    __tablename__ = "affiliate_conversions"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    affiliate_link_id = db.Column(UUID(as_uuid=True), db.ForeignKey("affiliate_links.id", ondelete="CASCADE"), nullable=False, index=True)
    order_value = db.Column(db.Integer, nullable=False)
    commission_amount = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(32), default="pending", nullable=False)

    __table_args__ = (
        Index("ix_conversion_status", "status"),
    )


class SubscriptionPlan(db.Model, TimestampMixin):
    __tablename__ = "subscription_plans"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    price = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(8), default="INR", nullable=False)
    benefits = db.Column(db.JSON, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    razorpay_plan_id = db.Column(db.String(80), nullable=True, unique=True)


class Subscription(db.Model, TimestampMixin):
    __tablename__ = "subscriptions"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscriber_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    creator_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id = db.Column(UUID(as_uuid=True), db.ForeignKey("subscription_plans.id", ondelete="SET NULL"), nullable=True)
    status = db.Column(db.String(32), default="active", nullable=False)
    razorpay_subscription_id = db.Column(db.String(80), nullable=True, unique=True)
    current_period_end = db.Column(db.DateTime, nullable=True)
    cancel_at_period_end = db.Column(db.Boolean, default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint("subscriber_id", "creator_id", name="uq_subscriber_creator"),
    )


class CreatorMarketplaceProfile(db.Model, TimestampMixin):
    __tablename__ = "creator_marketplace_profiles"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    # Use JSON to stay compatible with SQLite; treat as list of strings
    categories = db.Column(db.JSON, nullable=True)
    rate_card = db.Column(db.JSON, nullable=True)
    bio = db.Column(db.Text, nullable=True)
    availability_status = db.Column(db.String(32), default="open", nullable=False)


class MarketplaceOffer(db.Model, TimestampMixin):
    __tablename__ = "marketplace_offers"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    brand_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    message = db.Column(db.Text, nullable=False)
    amount_offered = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(32), default="open", nullable=False)
    thread_id = db.Column(UUID(as_uuid=True), db.ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (
        Index("ix_marketplace_status", "status"),
    )


class AdsRevenue(db.Model, TimestampMixin):
    __tablename__ = "ads_revenue"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id = db.Column(UUID(as_uuid=True), db.ForeignKey("ad_campaigns.id", ondelete="SET NULL"), nullable=True)
    rpm = db.Column(db.Integer, default=0, nullable=False)
    rpc = db.Column(db.Integer, default=0, nullable=False)
    impressions = db.Column(db.Integer, default=0, nullable=False)
    clicks = db.Column(db.Integer, default=0, nullable=False)
    earnings = db.Column(db.Integer, default=0, nullable=False)
    platform_fees = db.Column(db.Integer, default=0, nullable=False)


class LiveEarning(db.Model, TimestampMixin):
    __tablename__ = "live_earnings"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = db.Column(UUID(as_uuid=True), db.ForeignKey("live_sessions.id", ondelete="CASCADE"), nullable=False, unique=True)
    total_badges_amount = db.Column(db.Integer, default=0, nullable=False)
    platform_fee_amount = db.Column(db.Integer, default=0, nullable=False)
    creator_earnings = db.Column(db.Integer, default=0, nullable=False)
    currency = db.Column(db.String(8), default="INR", nullable=False)
