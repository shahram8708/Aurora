import uuid
from sqlalchemy import func
from flask import request, jsonify, render_template, abort, url_for, redirect, make_response
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import (
    AffiliateCommission,
    CommerceAffiliateLink,
    Product,
    AffiliateLink as MarketplaceAffiliateLink,
    AffiliateConversion as MarketplaceAffiliateConversion,
    Order,
    OrderItem,
)
from . import affiliate_bp
from .affiliate_service import create_affiliate_link, record_click, record_conversion


@affiliate_bp.post("/link")
@jwt_required()
def create_link():
    data = request.get_json(force=True)
    link = create_affiliate_link(get_jwt_identity(), data.get("product_id"))
    return jsonify({"code": link.unique_code})


@affiliate_bp.get("/mine")
@jwt_required()
def list_commerce_affiliates():
    """Return shop/commerce affiliate links, commissions, and totals for the current user."""
    try:
        user_id = uuid.UUID(str(get_jwt_identity()))
    except (ValueError, TypeError):
        abort(401)

    links = CommerceAffiliateLink.query.filter_by(user_id=user_id).all()
    links_by_id = {link.id: link for link in links}

    commissions_raw = (
        AffiliateCommission.query.join(CommerceAffiliateLink, AffiliateCommission.affiliate_id == CommerceAffiliateLink.id)
        .filter(CommerceAffiliateLink.user_id == user_id)
        .all()
    )

    product_ids = {link.product_id for link in links if link.product_id}
    for commission in commissions_raw:
        link = links_by_id.get(commission.affiliate_id)
        if link and link.product_id:
            product_ids.add(link.product_id)
    product_map = {p.id: p for p in Product.query.filter(Product.id.in_(product_ids)).all()} if product_ids else {}

    totals = {
        "clicks": sum(link.clicks for link in links),
        "conversions": sum(link.conversions for link in links),
        "earnings": sum(link.earnings for link in links),
        "pending_amount": sum(c.amount for c in commissions_raw if getattr(c, "status", "pending") == "pending"),
        "paid_amount": sum(c.amount for c in commissions_raw if getattr(c, "status", "pending") == "paid"),
    }

    share_links = {link.id: url_for("affiliate.click", code=link.unique_code, _external=True) for link in links}

    link_rows = [
        {
            "id": str(link.id),
            "product_id": str(link.product_id),
            "product_title": product_map.get(link.product_id).title if product_map.get(link.product_id) else "Product",
            "code": link.unique_code,
            "clicks": link.clicks,
            "conversions": link.conversions,
            "earnings": link.earnings,
            "share_url": share_links.get(link.id),
            "created_at": link.created_at.isoformat() if getattr(link, "created_at", None) else None,
        }
        for link in links
    ]

    commissions = [
        {
            "order_id": commission.order_id,
            "amount": commission.amount,
            "status": commission.status,
            "product_title": (product_map.get(getattr(links_by_id.get(commission.affiliate_id), "product_id", None)) or {}).title
            if links_by_id.get(commission.affiliate_id)
            else "Product",
            "code": links_by_id.get(commission.affiliate_id).unique_code if links_by_id.get(commission.affiliate_id) else None,
        }
        for commission in commissions_raw
    ]

    return jsonify({"links": link_rows, "commissions": commissions, "totals": totals, "share_links": share_links})


@affiliate_bp.get("/click/<code>")
def click(code):
    link = record_click(code)
    redirect_url = url_for("shop.product_detail", product_id=link.product_id)

    # Persist the affiliate code so checkout can attribute conversions without extra client work.
    response = make_response(redirect(redirect_url))
    response.set_cookie(
        "affiliate_code",
        code,
        max_age=7 * 24 * 3600,
        httponly=False,
        secure=False,
        samesite="Lax",
    )

    if request.args.get("format") == "json":
        response = jsonify({"redirect": redirect_url})
        response.set_cookie(
            "affiliate_code",
            code,
            max_age=7 * 24 * 3600,
            httponly=False,
            secure=False,
            samesite="Lax",
        )

    return response


@affiliate_bp.post("/convert")
@jwt_required()
def convert():
    data = request.get_json(force=True)
    commission = record_conversion(data.get("order_id"), data.get("code"))
    return jsonify({"id": str(commission.id) if commission else None})


@affiliate_bp.get("/dashboard")
@jwt_required()
def dashboard():
    try:
        user_id = uuid.UUID(str(get_jwt_identity()))
    except (ValueError, TypeError):
        abort(401)
    links = CommerceAffiliateLink.query.filter_by(user_id=user_id).all()
    links_by_id = {link.id: link for link in links}

    commissions_raw = (
        AffiliateCommission.query.join(CommerceAffiliateLink, AffiliateCommission.affiliate_id == CommerceAffiliateLink.id)
        .filter(CommerceAffiliateLink.user_id == user_id)
        .all()
    )

    product_ids = {link.product_id for link in links if link.product_id}
    for commission in commissions_raw:
        link = links_by_id.get(commission.affiliate_id)
        if link and link.product_id:
            product_ids.add(link.product_id)
    product_map = {p.id: p for p in Product.query.filter(Product.id.in_(product_ids)).all()} if product_ids else {}

    commissions = []
    for commission in commissions_raw:
        link = links_by_id.get(commission.affiliate_id)
        prod = product_map.get(getattr(link, "product_id", None)) if link else None
        commissions.append(
            {
                "order_id": commission.order_id,
                "amount": commission.amount,
                "status": commission.status,
                "product_title": prod.title if prod else "Product",
                "product_id": str(prod.id) if prod else None,
                "code": link.unique_code if link else None,
            }
        )

    commerce_totals = {
        "clicks": sum(link.clicks for link in links),
        "conversions": sum(link.conversions for link in links),
        "earnings": sum(link.earnings for link in links),
        "pending_amount": sum(c.amount for c in commissions_raw if getattr(c, "status", "pending") == "pending"),
        "paid_amount": sum(c.amount for c in commissions_raw if getattr(c, "status", "pending") == "paid"),
    }

    share_links = {link.id: url_for("affiliate.click", code=link.unique_code, _external=True) for link in links}

    marketplace_links = (
        MarketplaceAffiliateLink.query.filter_by(creator_id=user_id)
        .order_by(MarketplaceAffiliateLink.created_at.desc())
        .all()
    )
    marketplace_link_map = {link.id: link for link in marketplace_links}
    marketplace_conversions = (
        MarketplaceAffiliateConversion.query.join(MarketplaceAffiliateLink, MarketplaceAffiliateConversion.affiliate_link_id == MarketplaceAffiliateLink.id)
        .filter(MarketplaceAffiliateLink.creator_id == user_id)
        .order_by(MarketplaceAffiliateConversion.created_at.desc())
        .all()
    )
    marketplace_totals = {
        "clicks": sum(link.click_count for link in marketplace_links),
        "conversions": sum(link.conversion_count for link in marketplace_links),
        "earnings": sum((c.commission_amount or 0) for c in marketplace_conversions),
        "pending_amount": sum((c.commission_amount or 0) for c in marketplace_conversions if getattr(c, "status", "pending") != "paid"),
        "paid_amount": sum((c.commission_amount or 0) for c in marketplace_conversions if getattr(c, "status", "pending") == "paid"),
    }
    marketplace_share_links = {
        link.id: url_for("monetization.affiliate_redirect", slug=link.url_slug, _external=True)
        for link in marketplace_links
    }

    # Seller (shop) performance, reusing seller dashboard metrics
    active_statuses = ["paid", "processing", "shipped", "delivered"]
    seller_total_sales = (
        OrderItem.query.join(Order, OrderItem.order_id == Order.id)
        .filter(OrderItem.seller_id == user_id, Order.status.in_(active_statuses))
        .with_entities(func.coalesce(func.sum(OrderItem.quantity), 0))
        .scalar()
    )
    seller_total_revenue = (
        OrderItem.query.join(Order, OrderItem.order_id == Order.id)
        .filter(OrderItem.seller_id == user_id, Order.status.in_(active_statuses))
        .with_entities(func.coalesce(func.sum(OrderItem.price * OrderItem.quantity), 0))
        .scalar()
    )
    seller_pending_orders = (
        OrderItem.query.join(Order, OrderItem.order_id == Order.id)
        .filter(OrderItem.seller_id == user_id, Order.status.in_(["paid", "processing", "shipped"]))
        .count()
    )
    seller_completed_orders = (
        OrderItem.query.join(Order, OrderItem.order_id == Order.id)
        .filter(OrderItem.seller_id == user_id, Order.status == "delivered")
        .count()
    )
    seller_top_products = (
        OrderItem.query.join(Product, OrderItem.product_id == Product.id)
        .filter(OrderItem.seller_id == user_id)
        .with_entities(Product.id, Product.title, func.sum(OrderItem.quantity).label("qty"))
        .group_by(Product.id, Product.title)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(5)
        .all()
    )
    seller_totals = {
        "total_sales": seller_total_sales or 0,
        "total_revenue": seller_total_revenue or 0,
        "pending_orders": seller_pending_orders,
        "completed_orders": seller_completed_orders,
    }

    return render_template(
        "affiliate/dashboard.html",
        links=links,
        commissions=commissions,
        totals=commerce_totals,
        commerce_totals=commerce_totals,
        product_map=product_map,
        share_links=share_links,
        marketplace_links=marketplace_links,
        marketplace_conversions=marketplace_conversions,
        marketplace_link_map=marketplace_link_map,
        marketplace_totals=marketplace_totals,
        marketplace_share_links=marketplace_share_links,
        seller_totals=seller_totals,
        seller_top_products=seller_top_products,
    )
