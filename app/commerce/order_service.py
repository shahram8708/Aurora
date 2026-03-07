import uuid
from datetime import datetime
from flask import current_app
from sqlalchemy.orm import joinedload
from app.extensions import db
from app.models import Order, OrderItem, Cart, CartItem, ShipmentTracking
from .cart_service import get_cart, cart_totals, recalc_cart, clear_cart
from .inventory_service import attach_reservations_to_order, release_failed_order
from .razorpay_checkout_service import create_gateway_order, verify_payment_signature
from app.affiliate.affiliate_service import record_conversion


class OrderError(Exception):
    pass


def _as_uuid(value, label: str = "id") -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError) as exc:
        raise OrderError(f"Invalid {label}") from exc


def create_checkout_order(user_id: str, shipping_address: dict) -> tuple[Order, dict]:
    user_uuid = _as_uuid(user_id, "user_id")
    cart = get_cart(user_uuid)
    recalc_cart(cart)
    if not cart.items:
        raise OrderError("Cart is empty")

    # Basic shipping validation for required fields
    required_fields = {"name": "Full name", "phone": "Phone", "line1": "Address line", "city": "City", "zip": "ZIP"}
    missing = [label for key, label in required_fields.items() if not (shipping_address or {}).get(key)]
    if missing:
        raise OrderError(f"Shipping missing: {', '.join(missing)}")

    total = cart_totals(cart)
    order = Order(
        buyer_id=user_uuid,
        total_amount=total,
        currency="INR",
        status="pending",
        shipping_address_json=shipping_address,
    )
    db.session.add(order)
    db.session.flush()
    gateway_order = create_gateway_order(order)
    order.razorpay_order_id = gateway_order.get("id")
    db.session.commit()
    return order, gateway_order


def finalize_order_payment(order_id: str, payment_id: str, signature: str, affiliate_code: str | None = None):
    order_uuid = _as_uuid(order_id, "order_id")
    order = Order.query.options(joinedload(Order.items)).filter_by(id=order_uuid).with_for_update().first_or_404()
    return _finalize_order_payment(order, payment_id, signature, affiliate_code)


def finalize_order_payment_by_gateway_order(
    gateway_order_id: str, payment_id: str, signature: str, affiliate_code: str | None = None
):
    order = (
        Order.query.options(joinedload(Order.items))
        .filter_by(razorpay_order_id=gateway_order_id)
        .with_for_update()
        .first_or_404()
    )
    return _finalize_order_payment(order, payment_id, signature, affiliate_code)


def _finalize_order_payment(order: Order, payment_id: str, signature: str, affiliate_code: str | None):
    if order.status not in {"pending", "created"}:
        raise OrderError("Order already processed")
    verify_payment_signature(order.razorpay_order_id, payment_id, signature)
    cart = (
        Cart.query.options(joinedload(Cart.items).joinedload(CartItem.product))
        .filter_by(user_id=order.buyer_id)
        .first()
    )
    if not cart or not cart.items:
        raise OrderError("Cart empty")
    order.status = "paid"
    order.razorpay_payment_id = payment_id
    order.razorpay_signature = signature
    for item in cart.items:
        db.session.add(
            OrderItem(
                order_id=order.id,
                product_id=item.product_id,
                seller_id=item.product.seller_id if hasattr(item, "product") else None,
                quantity=item.quantity,
                price=item.price_snapshot,
            )
        )
    attach_reservations_to_order(cart.id, order.id)
    if affiliate_code:
        record_conversion(order.id, affiliate_code)
    clear_cart(order.buyer_id)
    db.session.commit()
    return order


def handle_payment_failure(order_id: str, reason: str | None = None):
    order = Order.query.filter_by(id=order_id).with_for_update().first()
    if not order:
        return
    order.status = "failed"
    order.razorpay_payment_id = None
    db.session.commit()
    release_failed_order(order_id)
    current_app.logger.warning("Order payment failed", extra={"order_id": str(order_id), "reason": reason})


def list_orders(user_id: str):
    buyer_uuid = _as_uuid(user_id, "user_id")
    return Order.query.options(joinedload(Order.items)).filter_by(buyer_id=buyer_uuid).order_by(Order.created_at.desc()).all()


def update_shipment(order_id: str, tracking_number: str, carrier: str, status: str):
    order_uuid = _as_uuid(order_id, "order_id")
    tracking = ShipmentTracking.query.filter_by(order_id=order_uuid).first()
    if not tracking:
        tracking = ShipmentTracking(order_id=order_uuid)
        db.session.add(tracking)
    tracking.tracking_number = tracking_number
    tracking.carrier = carrier
    tracking.status = status
    tracking.updated_at = datetime.utcnow()

    # Keep order status aligned with shipment status so completed count updates.
    order = Order.query.filter_by(id=order_uuid).with_for_update().first()
    if order and status:
        allowed = {"processing", "shipped", "delivered"}
        if status in allowed:
            order.status = status

    db.session.commit()
    return tracking
