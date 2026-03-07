import uuid
from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import UniqueConstraint, Index
from app.extensions import db
from .user import TimestampMixin


class PaymentTransaction(db.Model, TimestampMixin):
    __tablename__ = "payment_transactions"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    amount = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(8), default="INR", nullable=False)
    purpose = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(32), nullable=False, index=True)
    razorpay_order_id = db.Column(db.String(80), nullable=False, unique=True)
    razorpay_payment_id = db.Column(db.String(80), nullable=True, unique=True)
    razorpay_signature = db.Column(db.String(255), nullable=True)
    failure_reason = db.Column(db.String(255), nullable=True)
    metadata_json = db.Column(db.JSON, nullable=True)

    __table_args__ = (
        Index("ix_payment_purpose_status", "purpose", "status"),
    )


class PayoutRequest(db.Model, TimestampMixin):
    __tablename__ = "payout_requests"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(32), default="pending", nullable=False, index=True)
    processed_at = db.Column(db.DateTime, nullable=True)
    failure_reason = db.Column(db.String(255), nullable=True)
    reference_id = db.Column(db.String(80), nullable=True, unique=True)


class CreatorWallet(db.Model, TimestampMixin):
    __tablename__ = "creator_wallets"

    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    available_balance = db.Column(db.Integer, default=0, nullable=False)
    pending_payout = db.Column(db.Integer, default=0, nullable=False)
    lifetime_earnings = db.Column(db.Integer, default=0, nullable=False)
    lifetime_platform_fees = db.Column(db.Integer, default=0, nullable=False)
    last_earning_at = db.Column(db.DateTime, nullable=True)
