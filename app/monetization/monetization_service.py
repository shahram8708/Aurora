from datetime import datetime, timedelta
import uuid
import re
from razorpay.errors import BadRequestError
from flask import current_app
from app.extensions import db
from app.models import (
    BrandPartnership,
    AffiliateLink,
    AffiliateConversion,
    SubscriptionPlan,
    Subscription,
    CreatorMarketplaceProfile,
    MarketplaceOffer,
    CreatorWallet,
    PaymentTransaction,
    User,
    Post,
    Reel,
)


class MonetizationError(Exception):
    pass


def _to_uuid(value, field_name: str = "id"):
    try:
        return uuid.UUID(str(value)) if value is not None else None
    except (ValueError, TypeError):
        raise MonetizationError(f"Invalid {field_name}")


def _normalize_benefits(raw_benefits):
    if raw_benefits is None:
        return {}
    if isinstance(raw_benefits, dict):
        return dict(raw_benefits)
    if isinstance(raw_benefits, list):
        return {"perks": [b for b in raw_benefits if b]}
    return {}


def _active_plan_for_creator(creator_uuid):
    plan = (
        SubscriptionPlan.query.filter_by(creator_id=creator_uuid, is_active=True)
        .order_by(SubscriptionPlan.created_at.desc())
        .first()
    )
    if not plan:
        raise MonetizationError("Create a subscription plan first")
    return plan


def create_brand_partnership(creator_id: str, post_id: str | None, brand_name: str, metadata: dict | None) -> BrandPartnership:
    deal = BrandPartnership(
        creator_id=_to_uuid(creator_id, "creator_id"),
        post_id=_to_uuid(post_id, "post_id"),
        brand_name=brand_name,
        metadata_json=metadata or {},
    )
    db.session.add(deal)
    db.session.commit()
    return deal


def mark_brand_paid(deal_id: str, amount: int):
    deal = BrandPartnership.query.get_or_404(_to_uuid(deal_id, "deal_id"))
    deal.is_paid_partnership = True
    deal.agreed_amount = amount
    deal.status = "paid"
    db.session.commit()
    return deal


def _sanitize_slug(raw: str | None) -> str | None:
    if raw is None:
        return None
    slug = re.sub(r"[^a-z0-9-]", "-", str(raw).strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or None


def create_affiliate_link(creator_id: str, product_name: str, target_url: str, commission_rate: float, slug: str | None = None) -> AffiliateLink:
    requested_slug = _sanitize_slug(slug)
    candidate = requested_slug or uuid.uuid4().hex[:10]
    # Ensure uniqueness; regenerate if we randomly collide, but fail fast if user requested slug is taken.
    if requested_slug:
        exists = AffiliateLink.query.filter_by(url_slug=candidate).first()
        if exists:
            raise MonetizationError("Slug already in use")
    while AffiliateLink.query.filter_by(url_slug=candidate).first():
        candidate = uuid.uuid4().hex[:10]
    link = AffiliateLink(
        creator_id=_to_uuid(creator_id, "creator_id"),
        product_name=product_name,
        target_url=target_url,
        url_slug=candidate,
        commission_rate=commission_rate,
    )
    db.session.add(link)
    db.session.commit()
    return link


def record_affiliate_click(slug: str):
    link = AffiliateLink.query.filter_by(url_slug=slug).first_or_404()
    link.click_count += 1
    db.session.commit()
    return link


def record_affiliate_conversion(slug: str, order_value: int):
    link = AffiliateLink.query.filter_by(url_slug=slug).first_or_404()
    commission = int(order_value * link.commission_rate)
    conversion = AffiliateConversion(
        affiliate_link_id=link.id,
        order_value=order_value,
        commission_amount=commission,
        status="confirmed",
    )
    link.conversion_count += 1
    wallet = CreatorWallet.query.filter_by(user_id=link.creator_id).first()
    if not wallet:
        wallet = CreatorWallet(user_id=link.creator_id)
        db.session.add(wallet)
    # Guard against legacy nulls
    wallet.available_balance = (wallet.available_balance or 0) + commission
    wallet.lifetime_earnings = (wallet.lifetime_earnings or 0) + commission
    wallet.last_earning_at = datetime.utcnow()
    db.session.add(conversion)
    db.session.commit()
    return conversion


def create_subscription_plan(creator_id: str, price: int, benefits: dict | None):
    from app.payments.razorpay_service import create_subscription_plan as rp_create_subscription_plan

    creator_uuid = _to_uuid(creator_id, "creator_id")
    existing = SubscriptionPlan.query.filter_by(creator_id=creator_uuid, is_active=True).first()
    if existing:
        raise MonetizationError("You already have an active plan")
    plan = SubscriptionPlan(creator_id=creator_uuid, price=price, benefits=_normalize_benefits(benefits), currency="INR")
    db.session.add(plan)
    db.session.flush()
    rp_plan = rp_create_subscription_plan(price, plan.id)
    plan.razorpay_plan_id = rp_plan.get("id")
    db.session.commit()
    return plan


def list_subscription_plans(creator_id: str):
    creator_uuid = _to_uuid(creator_id, "creator_id")
    return (
        SubscriptionPlan.query.filter_by(creator_id=creator_uuid)
        .order_by(SubscriptionPlan.created_at.desc())
        .all()
    )


def get_subscription_status(subscriber_id: str, creator_id: str):
    subscriber_uuid = _to_uuid(subscriber_id, "subscriber_id")
    creator_uuid = _to_uuid(creator_id, "creator_id")
    sub = Subscription.query.filter_by(subscriber_id=subscriber_uuid, creator_id=creator_uuid).first()
    if not sub or sub.status not in ("active", "created"):
        return None
    return {
        "id": str(sub.id),
        "status": sub.status,
        "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
    }


def get_subscriber_content_selection(creator_id: str):
    creator_uuid = _to_uuid(creator_id, "creator_id")
    plan = (
        SubscriptionPlan.query.filter_by(creator_id=creator_uuid, is_active=True)
        .order_by(SubscriptionPlan.created_at.desc())
        .first()
    )
    if not plan:
        return {"plan_id": None, "posts": [], "reels": []}
    benefits = _normalize_benefits(plan.benefits)
    sel = benefits.get("subscriber_content") or {}
    posts = [str(pid) for pid in sel.get("posts", []) if pid]
    reels = [str(rid) for rid in sel.get("reels", []) if rid]
    return {"plan_id": str(plan.id), "posts": posts, "reels": reels}


def _post_thumbnail(post):
    media_list = getattr(post, "media", None)
    media = media_list[0] if media_list else None
    return (
        getattr(post, "thumbnail_url", None)
        or getattr(post, "cover_url", None)
        or (media.thumbnail_url if media else None)
        or (media.media_url if media else None)
        or getattr(post, "media_url", None)
    )


def _serialize_post_preview(post: Post) -> dict:
    media_list = getattr(post, "media", None)
    media = media_list[0] if media_list else None
    return {
        "id": str(post.id),
        "caption": post.caption or "Post",
        "thumb": _post_thumbnail(post) or "",
        "is_video": bool(getattr(post, "is_video", False) or (media and media.media_type == "video")),
        "created_at": post.created_at.isoformat() if getattr(post, "created_at", None) else None,
    }


def _serialize_reel_preview(reel: Reel) -> dict:
    return {
        "id": str(reel.id),
        "caption": reel.caption or "Reel",
        "thumb": reel.thumbnail_url or getattr(reel, "cover_url", None) or reel.video_url,
        "video_url": reel.video_url,
        "created_at": reel.created_at.isoformat() if getattr(reel, "created_at", None) else None,
    }


def update_subscriber_content_selection(creator_id: str, post_ids: list | None, reel_ids: list | None):
    creator_uuid = _to_uuid(creator_id, "creator_id")
    plan = _active_plan_for_creator(creator_uuid)
    post_uuid_list = [_to_uuid(pid, "post_id") for pid in (post_ids or []) if pid]
    reel_uuid_list = [_to_uuid(rid, "reel_id") for rid in (reel_ids or []) if rid]

    valid_posts = {
        str(p.id)
        for p in Post.query.filter(Post.id.in_(post_uuid_list), Post.user_id == creator_uuid, Post.is_archived.is_(False)).all()
    }
    valid_reels = {
        str(r.id)
        for r in Reel.query.filter(Reel.id.in_(reel_uuid_list), Reel.user_id == creator_uuid, Reel.is_published.is_(True)).all()
    }

    benefits = _normalize_benefits(plan.benefits)
    benefits["subscriber_content"] = {"posts": sorted(valid_posts), "reels": sorted(valid_reels)}
    plan.benefits = benefits
    db.session.commit()
    return {"plan_id": str(plan.id), "posts": sorted(valid_posts), "reels": sorted(valid_reels)}


def list_subscriber_content_options(creator_id: str):
    creator_uuid = _to_uuid(creator_id, "creator_id")
    plan = _active_plan_for_creator(creator_uuid)
    selection = get_subscriber_content_selection(str(creator_uuid))
    posts = (
        Post.query.filter_by(user_id=creator_uuid, is_archived=False)
        .order_by(Post.created_at.desc())
        .limit(120)
        .all()
    )
    reels = (
        Reel.query.filter_by(user_id=creator_uuid, is_published=True)
        .order_by(Reel.created_at.desc())
        .limit(120)
        .all()
    )
    return {
        "plan_id": str(plan.id),
        "selected": {"posts": selection.get("posts", []), "reels": selection.get("reels", [])},
        "posts": [_serialize_post_preview(p) for p in posts],
        "reels": [_serialize_reel_preview(r) for r in reels],
    }


def list_creator_subscribers(creator_id: str):
    creator_uuid = _to_uuid(creator_id, "creator_id")
    subs = (
        db.session.query(Subscription, User)
        .join(User, Subscription.subscriber_id == User.id)
        .filter(Subscription.creator_id == creator_uuid, Subscription.status.in_(["active", "created"]))
        .order_by(Subscription.created_at.desc())
        .all()
    )
    result = []
    for sub, user in subs:
        result.append(
            {
                "subscription_id": str(sub.id),
                "subscriber_id": str(user.id),
                "username": user.username,
                "status": sub.status,
                "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
            }
        )
    return result


def start_subscription_order(subscriber_id: str, creator_id: str, plan_id: str):
    from app.payments.razorpay_service import create_order_for_purpose

    plan = SubscriptionPlan.query.get_or_404(_to_uuid(plan_id, "plan_id"))
    subscriber_uuid = _to_uuid(subscriber_id, "subscriber_id")
    creator_uuid = _to_uuid(creator_id, "creator_id")
    existing = Subscription.query.filter_by(subscriber_id=subscriber_uuid, creator_id=creator_uuid).first()
    if existing and existing.status in ("active", "created"):
        raise MonetizationError("Already subscribed")
    notes = {
        "purpose": "creator_subscription",
        "plan_id": str(plan.id),
        "creator_id": str(creator_uuid),
        "buyer_id": str(subscriber_uuid),
    }
    order = create_order_for_purpose(plan.price, notes, receipt=f"sub-{plan.id}")
    return order, plan


def finalize_subscription_order(order_id: str, payment_id: str, signature: str):
    from app.payments.razorpay_service import verify_signature
    from app.models import PaymentTransaction  # local import to avoid circular

    txn = PaymentTransaction.query.filter_by(razorpay_order_id=order_id).first()
    if not txn:
        raise MonetizationError("Unknown subscription order")

    verify_signature(order_id, payment_id, signature)

    txn.razorpay_payment_id = payment_id
    txn.razorpay_signature = signature
    txn.status = "paid"

    notes = txn.metadata_json or {}
    plan_id = notes.get("plan_id")
    creator_id = notes.get("creator_id")
    subscriber_id = txn.user_id or notes.get("buyer_id") or notes.get("subscriber_id")
    if not plan_id or not creator_id or not subscriber_id:
        raise MonetizationError("Incomplete subscription metadata")

    plan = SubscriptionPlan.query.get_or_404(_to_uuid(plan_id, "plan_id"))
    subscriber_uuid = _to_uuid(subscriber_id, "subscriber_id")
    creator_uuid = _to_uuid(creator_id, "creator_id")

    existing = Subscription.query.filter_by(subscriber_id=subscriber_uuid, creator_id=creator_uuid).first()
    renew_until = datetime.utcnow() + timedelta(days=30)
    if existing:
        existing.plan_id = plan.id
        existing.status = "active"
        existing.current_period_end = renew_until
        existing.cancel_at_period_end = False
        existing.razorpay_subscription_id = None
        sub = existing
    else:
        sub = Subscription(
            subscriber_id=subscriber_uuid,
            creator_id=creator_uuid,
            plan_id=plan.id,
            status="active",
            razorpay_subscription_id=None,
            current_period_end=renew_until,
            cancel_at_period_end=False,
        )
        db.session.add(sub)

    # Tag transaction with subscription id for refunds/lookups.
    meta = txn.metadata_json or {}
    meta["subscription_id"] = str(sub.id)
    txn.metadata_json = meta
    db.session.add(txn)
    db.session.commit()
    return sub


def subscribe(subscriber_id: str, creator_id: str, plan_id: str):
    from app.payments.razorpay_service import create_subscription as rp_create_subscription

    plan = SubscriptionPlan.query.get_or_404(_to_uuid(plan_id, "plan_id"))
    subscriber_uuid = _to_uuid(subscriber_id, "subscriber_id")
    creator_uuid = _to_uuid(creator_id, "creator_id")
    existing = Subscription.query.filter_by(subscriber_id=subscriber_uuid, creator_id=creator_uuid).first()
    # If already subscribed (or pending) just reuse the record to avoid duplicate rows/charges.
    if existing and existing.status not in ("canceled", "expired"):
        return existing
    rp_sub = rp_create_subscription(plan.razorpay_plan_id, str(subscriber_uuid), str(creator_uuid))
    current_end_ts = rp_sub.get("current_end") or rp_sub.get("charge_at") or rp_sub.get("start_at")
    # If a prior subscription exists but was canceled/expired, reuse the row to satisfy the unique constraint.
    if existing:
        existing.plan_id = plan.id
        existing.status = "created"
        existing.razorpay_subscription_id = rp_sub.get("id")
        existing.current_period_end = datetime.fromtimestamp(current_end_ts) if current_end_ts else None
        existing.cancel_at_period_end = False
        sub = existing
    else:
        sub = Subscription(
            subscriber_id=subscriber_uuid,
            creator_id=creator_uuid,
            plan_id=plan.id,
            status="created",
            razorpay_subscription_id=rp_sub.get("id"),
            # Some statuses return None for current_end; fall back to other timestamps when available.
            current_period_end=datetime.fromtimestamp(current_end_ts) if current_end_ts else None,
        )
    txn = PaymentTransaction(
        user_id=subscriber_uuid,
        amount=plan.price,
        currency=plan.currency,
        purpose="subscription",
        status="created",
        razorpay_order_id=rp_sub.get("id"),
        metadata_json={"creator_id": creator_id, "plan_id": plan_id},
    )
    db.session.add(sub)
    db.session.add(txn)
    db.session.commit()
    return sub


def cancel_subscription(subscriber_id: str, subscription_id: str):
    from app.payments.razorpay_service import cancel_subscription as rp_cancel_subscription, refund_payment

    sub = Subscription.query.get_or_404(_to_uuid(subscription_id, "subscription_id"))
    if str(sub.subscriber_id) != str(subscriber_id):
        raise MonetizationError("Not allowed")
    if not sub.created_at:
        raise MonetizationError("Missing subscription start time")
    if datetime.utcnow() - sub.created_at > timedelta(days=7):
        raise MonetizationError("Cancellation window (7 days) expired")

    # Find the most recent payment txn for this subscription.
    from app.models import PaymentTransaction  # local import

    txn = (
        PaymentTransaction.query.filter(
            PaymentTransaction.user_id == sub.subscriber_id,
            PaymentTransaction.purpose.in_(["subscription", "creator_subscription"]),
        )
        .order_by(PaymentTransaction.created_at.desc())
        .first()
    )

    # Ensure this transaction belongs to this subscription if metadata present.
    if txn and txn.metadata_json and txn.metadata_json.get("subscription_id") not in (None, str(sub.id)):
        txn = None

    # Refund when a payment exists; ignore "already refunded" errors; otherwise still cancel immediately so benefits stop.
    if txn and txn.razorpay_payment_id:
        try:
            refund_payment(txn.razorpay_payment_id, txn.amount)
            txn.status = "refunded"
        except BadRequestError as exc:
            # Treat already-refunded as best-effort cancel.
            if "fully refunded" in str(exc).lower():
                txn.status = "refunded"
            else:
                raise
    elif txn:
        txn.status = "canceled"

    if sub.razorpay_subscription_id:
        rp_cancel_subscription(sub.razorpay_subscription_id)

    sub.status = "canceled"
    sub.cancel_at_period_end = False
    sub.current_period_end = None
    sub.razorpay_subscription_id = None
    db.session.commit()
    return sub


def handle_subscription_webhook(payload: dict, signature: str, body: bytes):
    from app.payments.razorpay_service import verify_webhook_signature

    verify_webhook_signature(body, signature)
    event = payload.get("event")
    entity = payload.get("payload", {}).get("subscription", {}).get("entity", {})
    rp_sub_id = entity.get("id")
    status = entity.get("status")
    sub = Subscription.query.filter_by(razorpay_subscription_id=rp_sub_id).first()
    if not sub:
        return
    sub.status = status
    sub.current_period_end = datetime.fromtimestamp(entity.get("current_end")) if entity.get("current_end") else sub.current_period_end
    if status == "completed":
        wallet = CreatorWallet.query.filter_by(user_id=sub.creator_id).first()
        if not wallet:
            wallet = CreatorWallet(user_id=sub.creator_id)
            db.session.add(wallet)
        wallet.available_balance += SubscriptionPlan.query.get(sub.plan_id).price
    db.session.commit()


def ensure_marketplace_profile(user_id: str, categories: list[str] | None, bio: str | None, rate_card: dict | None):
    user_uuid = _to_uuid(user_id, "user_id")
    profile = CreatorMarketplaceProfile.query.filter_by(user_id=user_uuid).first()
    if not profile:
        profile = CreatorMarketplaceProfile(user_id=user_uuid)
        db.session.add(profile)
    profile.categories = categories or profile.categories
    profile.bio = bio or profile.bio
    profile.rate_card = rate_card or profile.rate_card
    db.session.commit()
    return profile


def create_offer(creator_id: str, brand_id: str, message: str, amount_offered: int | None, thread_id: str | None = None):
    offer = MarketplaceOffer(
        creator_id=_to_uuid(creator_id, "creator_id"),
        brand_id=_to_uuid(brand_id, "brand_id"),
        message=message,
        amount_offered=amount_offered,
        thread_id=_to_uuid(thread_id, "thread_id"),
    )
    db.session.add(offer)
    db.session.commit()
    return offer
