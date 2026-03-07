from datetime import datetime
from sqlalchemy import and_
from app.extensions import db
from app.models import Product, InventoryReservation


class InventoryError(Exception):
    pass


def lock_stock_for_cart(product: Product, quantity: int, cart_id: str):
    if product.stock_quantity < quantity:
        raise InventoryError("Insufficient stock")
    product.stock_quantity -= quantity
    res = InventoryReservation(product_id=product.id, quantity=quantity, cart_id=cart_id)
    db.session.add(res)


def release_cart_locks(cart_id: str, product_id: str | None = None, quantity: int | None = None):
    query = InventoryReservation.query.filter_by(cart_id=cart_id, status="locked")
    if product_id:
        query = query.filter_by(product_id=product_id)
    reservations = query.with_for_update().all()
    for res in reservations:
        release_qty = quantity if quantity is not None else res.quantity
        res.status = "released"
        prod = Product.query.with_for_update().get(res.product_id)
        if prod:
            prod.stock_quantity += release_qty
        if quantity is not None and release_qty < res.quantity:
            res.quantity -= release_qty
            res.status = "locked"
            continue
        db.session.delete(res)


def attach_reservations_to_order(cart_id: str, order_id: str):
    reservations = InventoryReservation.query.filter_by(cart_id=cart_id, status="locked").with_for_update().all()
    for res in reservations:
        res.order_id = order_id
        res.status = "committed"
    db.session.commit()


def release_failed_order(order_id: str):
    reservations = InventoryReservation.query.filter_by(order_id=order_id).with_for_update().all()
    for res in reservations:
        prod = Product.query.with_for_update().get(res.product_id)
        if prod:
            prod.stock_quantity += res.quantity
        res.status = "released"
        db.session.delete(res)
    db.session.commit()


def expire_reservations():
    expired = InventoryReservation.query.filter(and_(InventoryReservation.status == "locked", InventoryReservation.expires_at <= datetime.utcnow())).with_for_update().all()
    for res in expired:
        prod = Product.query.with_for_update().get(res.product_id)
        if prod:
            prod.stock_quantity += res.quantity
        res.status = "expired"
        db.session.delete(res)
    db.session.commit()
