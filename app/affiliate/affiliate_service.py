import uuid
from flask import current_app
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from app.extensions import db
from app.models import (
    Product,
    AffiliateProgram,
    CommerceAffiliateLink,
    AffiliateCommission,
    Order,
    CreatorWallet,
)


class AffiliateError(Exception):
    pass


def _as_uuid(value, field_name: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError) as exc:
        raise AffiliateError(f"Invalid {field_name}") from exc


def ensure_program(product_id: str, commission_percentage: float | None = None) -> AffiliateProgram:
    product_uuid = _as_uuid(product_id, "product_id")
    program = AffiliateProgram.query.filter_by(product_id=product_uuid).first()
    if not program:
        program = AffiliateProgram(product_id=product_uuid, commission_percentage=commission_percentage or 10.0)
        db.session.add(program)
        db.session.commit()
    return program


def create_affiliate_link(user_id: str, product_id: str) -> CommerceAffiliateLink:
    user_uuid = _as_uuid(user_id, "user_id")
    product_uuid = _as_uuid(product_id, "product_id")
    product = Product.query.get_or_404(product_uuid)
    if str(product.seller_id) == str(user_uuid):
        raise AffiliateError("Self-affiliate not allowed")
    ensure_program(product_uuid)
    existing = CommerceAffiliateLink.query.filter_by(user_id=user_uuid, product_id=product_uuid).first()
    if existing:
        return existing
    code = uuid.uuid4().hex[:12]
    link = CommerceAffiliateLink(user_id=user_uuid, product_id=product_uuid, unique_code=code)
    db.session.add(link)
    db.session.commit()
    return link


def record_click(code: str):
    link = CommerceAffiliateLink.query.filter_by(unique_code=code).first_or_404()
    link.clicks = link.clicks + 1
    db.session.commit()
    return link


def record_conversion(order_id: str, affiliate_code: str):
    order_uuid = _as_uuid(order_id, "order_id")
    link = CommerceAffiliateLink.query.filter_by(unique_code=affiliate_code).first()
    if not link:
        return None
    order = Order.query.options(joinedload(Order.items)).get(order_uuid)
    if not order:
        return None
    if str(order.buyer_id) == str(link.user_id):
        current_app.logger.warning("Self conversion ignored", extra={"order_id": str(order.id)})
        return None
    if not order.items:
        return None
    commission_amount = 0
    for item in order.items:
        program = AffiliateProgram.query.filter_by(product_id=item.product_id).first()
        if program and program.is_active:
            commission_amount += int(item.price * item.quantity * (program.commission_percentage / 100))
    exists = AffiliateCommission.query.filter_by(affiliate_id=link.id, order_id=order.id).first()
    if exists:
        return exists
    commission = AffiliateCommission(
        affiliate_id=link.id,
        order_id=order.id,
        amount=commission_amount,
        status="earned",
    )
    link.conversions += 1
    link.earnings += commission_amount
    wallet = CreatorWallet.query.filter_by(user_id=link.user_id).first()
    if not wallet:
        wallet = CreatorWallet(user_id=link.user_id)
        db.session.add(wallet)
    wallet.available_balance += commission_amount
    wallet.lifetime_earnings += commission_amount
    db.session.add(commission)
    db.session.commit()
    return commission
