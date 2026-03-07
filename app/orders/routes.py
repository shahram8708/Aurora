import uuid
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from flask import render_template, jsonify, request, abort, flash, redirect, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import csrf
from app.models import Order, OrderItem, ShipmentTracking, Product
from . import orders_bp
from app.commerce.order_service import list_orders, update_shipment


@orders_bp.get("/history")
@jwt_required()
def history():
    orders = list_orders(get_jwt_identity())
    return render_template("orders/history.html", orders=orders)


@orders_bp.get("/<uuid:order_id>/tracking")
@jwt_required()
def tracking(order_id):
    order = Order.query.filter_by(id=order_id).first()
    if not order:
        abort(404)
    tracking_obj = ShipmentTracking.query.filter_by(order_id=order_id).first()
    return render_template(
        "orders/tracking.html",
        order=order,
        tracking=tracking_obj,
        tracking_number=getattr(tracking_obj, "tracking_number", None),
        carrier=getattr(tracking_obj, "carrier", None),
        status=getattr(tracking_obj, "status", "pending"),
        updated_at=getattr(tracking_obj, "updated_at", None),
    )


@orders_bp.post("/<uuid:order_id>/shipment")
@csrf.exempt
@jwt_required()
def shipment_update(order_id):
    data = request.get_json(silent=True) or request.form
    tracking_obj = update_shipment(order_id, data.get("tracking_number"), data.get("carrier"), data.get("status"))
    flash("Shipment updated", "success")
    return redirect(url_for("orders.seller_dashboard"))


@orders_bp.get("/seller/dashboard")
@jwt_required()
def seller_dashboard():
    seller_identity = get_jwt_identity()
    try:
        seller_id = seller_identity if isinstance(seller_identity, uuid.UUID) else uuid.UUID(str(seller_identity))
    except (ValueError, TypeError):
        abort(401)
    active_statuses = ["paid", "processing", "shipped", "delivered"]
    total_sales = (
        OrderItem.query.join(Order, OrderItem.order_id == Order.id)
        .filter(OrderItem.seller_id == seller_id, Order.status.in_(active_statuses))
        .with_entities(func.coalesce(func.sum(OrderItem.quantity), 0))
        .scalar()
    )
    total_revenue = (
        OrderItem.query.join(Order, OrderItem.order_id == Order.id)
        .filter(OrderItem.seller_id == seller_id, Order.status.in_(active_statuses))
        .with_entities(func.coalesce(func.sum(OrderItem.price * OrderItem.quantity), 0))
        .scalar()
    )
    pending_orders = (
        OrderItem.query.join(Order, OrderItem.order_id == Order.id)
        .filter(OrderItem.seller_id == seller_id, Order.status.in_(["paid", "processing", "shipped"]))
        .count()
    )
    completed_orders = (
        OrderItem.query.join(Order, OrderItem.order_id == Order.id)
        .filter(OrderItem.seller_id == seller_id, Order.status == "delivered")
        .count()
    )
    # Orders list for fulfillment/history (show delivered too)
    seller_orders = (
        Order.query.join(OrderItem, OrderItem.order_id == Order.id)
        .filter(OrderItem.seller_id == seller_id, Order.status.in_(active_statuses))
        .options(joinedload(Order.items))
        .order_by(Order.created_at.desc())
        .all()
    )
    order_ids = [o.id for o in seller_orders]
    tracking_map = {
        t.order_id: t
        for t in ShipmentTracking.query.filter(ShipmentTracking.order_id.in_(order_ids)).all()
    } if order_ids else {}
    top_products = (
        OrderItem.query.join(Product, OrderItem.product_id == Product.id)
        .filter(OrderItem.seller_id == seller_id)
        .with_entities(Product.id, Product.title, func.sum(OrderItem.quantity).label("qty"))
        .group_by(Product.id, Product.title)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(5)
        .all()
    )
    return render_template(
        "orders/seller_dashboard.html",
        total_sales=total_sales,
        total_revenue=total_revenue,
        pending_orders=pending_orders,
        completed_orders=completed_orders,
        top_products=top_products,
        seller_orders=seller_orders,
        tracking_map=tracking_map,
    )
