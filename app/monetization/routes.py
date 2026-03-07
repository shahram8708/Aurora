import re
import uuid
from sqlalchemy import or_
from flask import request, jsonify, abort, render_template, current_app, url_for, redirect
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import limiter, csrf
from app.models import AffiliateLink, User, Post, BrandPartnership, MarketplaceOffer, CreatorMarketplaceProfile
from . import monetization_bp
from .monetization_service import (
    create_brand_partnership,
    mark_brand_paid,
    create_affiliate_link,
    record_affiliate_click,
    record_affiliate_conversion,
    create_subscription_plan,
    list_subscription_plans,
    subscribe,
    cancel_subscription,
    start_subscription_order,
    finalize_subscription_order,
    get_subscription_status,
    list_creator_subscribers,
    list_subscriber_content_options,
    update_subscriber_content_selection,
    ensure_marketplace_profile,
    create_offer,
    MonetizationError,
)


UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def _current_user_label():
    try:
        user = User.query.get(uuid.UUID(str(get_jwt_identity())))
        if user:
            return user.name or user.username
    except Exception:  # pylint: disable=broad-except
        return None
    return None


def _current_user_uuid():
    try:
        return uuid.UUID(str(get_jwt_identity()))
    except Exception:  # pylint: disable=broad-except
        abort(401, description="Invalid user")


def _creator_from_username(raw_username: str) -> User:
    handle = (raw_username or "").strip().lstrip("@")
    if not handle:
        abort(400, description="Creator username is required")
    user = User.query.filter_by(username=handle).first()
    if not user:
        abort(404, description="Creator not found")
    return user


def _post_id_from_reference(raw: str | None):
    if not raw:
        return None
    match = UUID_RE.search(str(raw))
    if match:
        return uuid.UUID(match.group(0))
    try:
        return uuid.UUID(str(raw))
    except Exception:  # pylint: disable=broad-except
        abort(400, description="Provide a valid post link or id")


def _kv_text_to_dict(raw):
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    text = str(raw)
    parts = re.split(r"[\n,]+", text)
    data = {}
    for part in parts:
        if not part.strip():
            continue
        if ":" in part:
            key, value = part.split(":", 1)
        elif "=" in part:
            key, value = part.split("=", 1)
        else:
            key, value = part, ""
        data[key.strip()] = value.strip()
    return data


def _categories_from_payload(raw):
    if raw is None:
        return []
    if isinstance(raw, list):
        return [c for c in raw if c]
    return [c.strip() for c in str(raw).split(",") if c.strip()]


@monetization_bp.post("/brand")
@jwt_required()
def brand_partnership():
    data = request.get_json(force=True)
    creator = _creator_from_username(data.get("creator_username") or data.get("creator"))
    post_uuid = _post_id_from_reference(data.get("post_url") or data.get("post_id"))
    post = Post.query.get_or_404(post_uuid) if post_uuid else None
    if post and post.user_id != creator.id:
        abort(400, description="Post does not belong to the creator")
    metadata = _kv_text_to_dict(data.get("metadata_text") or data.get("metadata"))
    brand_name = data.get("brand_name") or _current_user_label() or "Brand partner"
    deal = create_brand_partnership(str(creator.id), str(post.id) if post else None, brand_name, metadata)
    return jsonify({"id": str(deal.id), "creator_username": creator.username, "post_id": str(post.id) if post else None})


@monetization_bp.post("/brand/<uuid:deal_id>/paid")
@jwt_required()
def brand_paid(deal_id):
    data = request.get_json(force=True)
    deal = mark_brand_paid(deal_id, int(data.get("amount")))
    return jsonify({"id": str(deal.id), "status": deal.status})


@monetization_bp.get("/brand")
@jwt_required()
def list_brand_deals():
    uid = _current_user_uuid()
    deals = (
        BrandPartnership.query.filter(
            or_(BrandPartnership.creator_id == uid, BrandPartnership.brand_name == _current_user_label())
        )
        .order_by(BrandPartnership.created_at.desc())
        .all()
    )
    return jsonify(
        [
            {
                "id": str(d.id),
                "creator_id": str(d.creator_id),
                "post_id": str(d.post_id) if d.post_id else None,
                "brand_name": d.brand_name,
                "metadata": d.metadata_json or {},
                "status": d.status,
                "agreed_amount": d.agreed_amount,
                "is_paid": d.is_paid_partnership,
                "created_at": d.created_at.isoformat() if getattr(d, "created_at", None) else None,
            }
            for d in deals
        ]
    )


@monetization_bp.post("/affiliate")
@jwt_required()
@limiter.limit("20 per day")
def create_affiliate():
    data = request.get_json(force=True)
    try:
        link = create_affiliate_link(
            get_jwt_identity(),
            data.get("product_name"),
            data.get("target_url"),
            float(data.get("commission_rate", 0.1)),
            data.get("slug"),
        )
        return jsonify({"slug": link.url_slug})
    except MonetizationError as exc:
        return jsonify({"error": str(exc)}), 400


@monetization_bp.get("/affiliate/mine")
@jwt_required()
def list_affiliate_links():
    uid = _current_user_uuid()
    links = (
        AffiliateLink.query.filter_by(creator_id=uid)
        .order_by(AffiliateLink.created_at.desc())
        .all()
    )
    return jsonify(
        [
            {
                "slug": l.url_slug,
                "product_name": l.product_name,
                "target_url": l.target_url,
                "clicks": l.click_count,
                "conversions": l.conversion_count,
                "commission_rate": l.commission_rate,
                "created_at": l.created_at.isoformat() if getattr(l, "created_at", None) else None,
            }
            for l in links
        ]
    )


@monetization_bp.get("/affiliate/<slug>")
def affiliate_redirect(slug):
    record_affiliate_click(slug)
    link = AffiliateLink.query.filter_by(url_slug=slug).first_or_404()
    return redirect(link.target_url)


@monetization_bp.post("/affiliate/<slug>/convert")
def affiliate_convert(slug):
    data = request.get_json(force=True)
    conversion = record_affiliate_conversion(slug, int(data.get("order_value")))
    return jsonify({"id": str(conversion.id)})


@monetization_bp.post("/subscriptions/plan")
@jwt_required()
@limiter.limit("5 per day")
def create_plan():
    data = request.get_json(force=True)
    try:
        plan = create_subscription_plan(get_jwt_identity(), int(data.get("price")), data.get("benefits"))
        return jsonify({"id": str(plan.id), "razorpay_plan_id": plan.razorpay_plan_id})
    except MonetizationError as exc:
        return jsonify({"error": str(exc)}), 400


@monetization_bp.get("/subscriptions/plans")
@jwt_required()
def list_plans():
    plans = list_subscription_plans(get_jwt_identity())
    return jsonify(
        [
            {
                "id": str(p.id),
                "price": p.price,
                "currency": p.currency,
                "benefits": p.benefits or [],
                "razorpay_plan_id": p.razorpay_plan_id,
            }
            for p in plans
        ]
    )


@monetization_bp.get("/subscriptions/content")
@jwt_required()
def subscription_content_options():
    try:
        return jsonify(list_subscriber_content_options(get_jwt_identity()))
    except MonetizationError as exc:
        return jsonify({"error": str(exc)}), 400


@monetization_bp.post("/subscriptions/content")
@jwt_required()
def subscription_content_update():
    data = request.get_json(force=True)
    try:
        sel = update_subscriber_content_selection(
            get_jwt_identity(),
            data.get("posts") or [],
            data.get("reels") or [],
        )
        return jsonify(sel)
    except MonetizationError as exc:
        return jsonify({"error": str(exc)}), 400


@monetization_bp.post("/subscriptions/subscribe")
@jwt_required()
def subscribe_route():
    data = request.get_json(force=True)
    sub = subscribe(get_jwt_identity(), data.get("creator_id"), data.get("plan_id"))
    return jsonify({"id": str(sub.id), "razorpay_subscription_id": sub.razorpay_subscription_id})


@monetization_bp.post("/subscriptions/subscribe/order/start")
@jwt_required()
def subscribe_order_start():
    data = request.get_json(force=True)
    try:
        order, plan = start_subscription_order(get_jwt_identity(), data.get("creator_id"), data.get("plan_id"))
        return jsonify({"order_id": order.get("id"), "razorpay_order": order, "plan_price": plan.price, "currency": plan.currency})
    except MonetizationError as exc:
        return jsonify({"error": str(exc)}), 400


@monetization_bp.post("/subscriptions/subscribe/order/verify")
@jwt_required()
def subscribe_order_verify():
    data = request.get_json(force=True)
    try:
        sub = finalize_subscription_order(data.get("order_id"), data.get("payment_id"), data.get("signature"))
        return jsonify({"status": sub.status})
    except Exception as exc:  # pylint: disable=broad-except
        return jsonify({"error": str(exc)}), 400


@monetization_bp.get("/subscriptions/creator/subscribers")
@jwt_required()
def creator_subscribers():
    subs = list_creator_subscribers(get_jwt_identity())
    return jsonify(subs)


@monetization_bp.get("/subscriptions/plans/<uuid:creator_id>")
def list_creator_plans(creator_id):
    plans = list_subscription_plans(str(creator_id))
    return jsonify(
        [
            {
                "id": str(p.id),
                "price": p.price,
                "currency": p.currency,
                "benefits": p.benefits or [],
                "razorpay_plan_id": p.razorpay_plan_id,
            }
            for p in plans
        ]
    )


@monetization_bp.get("/subscriptions/status/<uuid:creator_id>")
@jwt_required()
def subscription_status(creator_id):
    status = get_subscription_status(get_jwt_identity(), str(creator_id))
    if not status:
        return jsonify({"subscribed": False})
    return jsonify({"subscribed": True, **status})


@monetization_bp.get("/subscriptions/checkout/meta")
@jwt_required(optional=True)
def subscription_checkout_meta():
    return jsonify(
        {
            "razorpay_key": current_app.config.get("RAZORPAY_KEY_ID"),
            "callback_url": url_for("commerce.checkout_callback", _external=True),
            "subscription_callback_url": url_for("monetization.subscribe_callback", _external=True),
        }
    )


@monetization_bp.route("/subscriptions/subscribe/callback", methods=["GET", "POST"])
@csrf.exempt
@jwt_required(optional=True)
def subscribe_callback():
    payload = request.values
    rp_order_id = payload.get("razorpay_order_id") or payload.get("order_id")
    rp_payment_id = payload.get("razorpay_payment_id")
    rp_signature = payload.get("razorpay_signature")
    err_desc = (
        payload.get("error[description]")
        or payload.get("error_description")
        or payload.get("error")
        or payload.get("error[code]")
    )

    if not rp_order_id:
        return render_template("commerce/checkout_result.html", status="error", message="Missing Razorpay order id."), 400

    try:
        if rp_payment_id and rp_signature:
            sub = finalize_subscription_order(rp_order_id, rp_payment_id, rp_signature)
            return render_template("commerce/checkout_result.html", status="success", message="Subscription active.", order=sub)

        failure_reason = err_desc or "Payment cancelled or failed."
        return render_template("commerce/checkout_result.html", status="error", message=failure_reason), 400
    except Exception as exc:  # pylint: disable=broad-except
        current_app.logger.exception("Subscription callback failed", extra={"razorpay_order_id": rp_order_id})
        return (
            render_template(
                "commerce/checkout_result.html",
                status="error",
                message=str(exc) or "Unable to finalize subscription payment.",
            ),
            400,
        )


@monetization_bp.post("/subscriptions/<uuid:subscription_id>/cancel")
@jwt_required()
def cancel_route(subscription_id):
    try:
        sub = cancel_subscription(get_jwt_identity(), subscription_id)
        return jsonify({"status": sub.status})
    except MonetizationError as exc:
        return jsonify({"error": str(exc)}), 400


@monetization_bp.post("/marketplace/profile")
@jwt_required()
def profile():
    data = request.get_json(force=True)
    profile_obj = ensure_marketplace_profile(
        get_jwt_identity(),
        _categories_from_payload(data.get("categories_text") or data.get("categories")),
        data.get("bio"),
        _kv_text_to_dict(data.get("rate_card_text") or data.get("rate_card")),
    )
    return jsonify({"id": str(profile_obj.id)})


@monetization_bp.get("/marketplace/profile")
@jwt_required()
def get_profile():
    user_uuid = _current_user_uuid()
    profile_obj = CreatorMarketplaceProfile.query.filter_by(user_id=user_uuid).first()
    if not profile_obj:
        return jsonify({})
    return jsonify(
        {
            "id": str(profile_obj.id),
            "categories": profile_obj.categories or [],
            "bio": profile_obj.bio,
            "rate_card": profile_obj.rate_card or {},
            "availability_status": profile_obj.availability_status,
            "updated_at": profile_obj.updated_at.isoformat() if getattr(profile_obj, "updated_at", None) else None,
        }
    )


@monetization_bp.post("/marketplace/offer")
@jwt_required()
def offer():
    data = request.get_json(force=True)
    offer_obj = create_offer(
        str(_creator_from_username(data.get("creator_username") or data.get("creator_id")).id),
        get_jwt_identity(),
        data.get("message"),
        data.get("amount_offered"),
        data.get("thread_id"),
    )
    return jsonify({"id": str(offer_obj.id)})


@monetization_bp.get("/marketplace/offers")
@jwt_required()
def list_offers():
    user_uuid = _current_user_uuid()
    offers = (
        MarketplaceOffer.query.filter(or_(MarketplaceOffer.brand_id == user_uuid, MarketplaceOffer.creator_id == user_uuid))
        .order_by(MarketplaceOffer.created_at.desc())
        .all()
    )
    return jsonify(
        [
            {
                "id": str(o.id),
                "creator_id": str(o.creator_id),
                "brand_id": str(o.brand_id),
                "role": "brand" if o.brand_id == user_uuid else "creator",
                "message": o.message,
                "amount_offered": o.amount_offered,
                "status": o.status,
                "created_at": o.created_at.isoformat() if getattr(o, "created_at", None) else None,
            }
            for o in offers
        ]
    )


@monetization_bp.get("/marketplace")
def marketplace_page():
    return render_template("monetization/marketplace.html")


@monetization_bp.get("/subscriptions")
def subscriptions_page():
    return render_template("monetization/subscriptions.html")
