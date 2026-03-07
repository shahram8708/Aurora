import uuid
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from flask import current_app
from app.extensions import db
from app.models import Cart, CartItem, Product
from .inventory_service import lock_stock_for_cart, release_cart_locks


class CartError(Exception):
    pass


def _as_uuid(value, label: str = "id") -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError) as exc:
        raise CartError(f"Invalid {label}") from exc


def get_cart(user_id: str) -> Cart:
    user_uuid = _as_uuid(user_id, "user_id")
    cart = Cart.query.options(joinedload(Cart.items)).filter_by(user_id=user_uuid).first()
    if cart:
        return cart
    cart = Cart(user_id=user_uuid)
    db.session.add(cart)
    db.session.commit()
    return cart


def _load_cart_for_update(cart_id: str) -> Cart:
    cart_uuid = _as_uuid(cart_id, "cart_id")
    stmt = select(Cart).options(joinedload(Cart.items)).where(Cart.id == cart_uuid).with_for_update()
    cart = db.session.execute(stmt).unique().scalar_one_or_none()
    if not cart:
        raise CartError("Cart not found")
    return cart


def add_item(user_id: str, product_id: str, quantity: int) -> Cart:
    user_uuid = _as_uuid(user_id, "user_id")
    product_uuid = _as_uuid(product_id, "product_id")
    cart = get_cart(user_uuid)
    cart = _load_cart_for_update(cart.id)
    product = Product.query.with_for_update().get(product_uuid)
    if not product or product.is_deleted or not product.is_active:
        raise CartError("Product unavailable")
    if quantity <= 0:
        raise CartError("Invalid quantity")
    if product.stock_quantity < quantity:
        raise CartError("Insufficient stock")
    item = next((i for i in cart.items if i.product_id == product_uuid), None)
    if item:
        item.quantity += quantity
    else:
        item = CartItem(cart_id=cart.id, product_id=product_uuid, quantity=quantity, price_snapshot=product.price)
        db.session.add(item)
    lock_stock_for_cart(product, quantity, cart.id)
    db.session.commit()
    return cart


def update_item(user_id: str, product_id: str, quantity: int) -> Cart:
    user_uuid = _as_uuid(user_id, "user_id")
    product_uuid = _as_uuid(product_id, "product_id")
    cart = get_cart(user_uuid)
    cart = _load_cart_for_update(cart.id)
    item = next((i for i in cart.items if i.product_id == product_uuid), None)
    if not item:
        raise CartError("Item not in cart")
    if quantity <= 0:
        db.session.delete(item)
        release_cart_locks(cart.id, product_uuid)
    else:
        product = Product.query.with_for_update().get(product_uuid)
        if not product or product.is_deleted or not product.is_active:
            raise CartError("Product unavailable")
        if product.stock_quantity < quantity:
            raise CartError("Insufficient stock")
        delta = quantity - item.quantity
        if delta > 0:
            lock_stock_for_cart(product, delta, cart.id)
        elif delta < 0:
            release_cart_locks(cart.id, product_uuid, -delta)
        item.quantity = quantity
        item.price_snapshot = product.price
    db.session.commit()
    return cart


def remove_item(user_id: str, product_id: str) -> Cart:
    user_uuid = _as_uuid(user_id, "user_id")
    product_uuid = _as_uuid(product_id, "product_id")
    cart = get_cart(user_uuid)
    cart = _load_cart_for_update(cart.id)
    for item in list(cart.items):
        if item.product_id == product_uuid:
            db.session.delete(item)
            release_cart_locks(cart.id, product_uuid)
    db.session.commit()
    return cart


def clear_cart(user_id: str):
    user_uuid = _as_uuid(user_id, "user_id")
    cart = get_cart(user_uuid)
    release_cart_locks(cart.id)
    CartItem.query.filter_by(cart_id=cart.id).delete()
    db.session.commit()


def cart_totals(cart: Cart) -> int:
    total = 0
    for item in cart.items:
        total += item.price_snapshot * item.quantity
    return total


def refresh_prices(cart: Cart):
    for item in cart.items:
        product = Product.query.get(item.product_id)
        if not product or product.is_deleted or not product.is_active:
            raise CartError("Product unavailable")
        item.price_snapshot = product.price
    db.session.commit()


def recalc_cart(cart: Cart) -> Cart:
    refresh_prices(cart)
    current_app.logger.debug("Cart recalculated", extra={"cart_id": str(cart.id)})
    return cart
