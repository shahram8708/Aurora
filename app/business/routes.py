from datetime import datetime
from flask import render_template, request, jsonify, abort
from flask_jwt_extended import jwt_required, get_jwt_identity
import uuid
from app.models import User, AdCampaign, PaymentTransaction
from app.payments.razorpay_service import create_order_for_purpose
from . import business_bp
from .analytics_service import get_insights, content_analytics, ads_performance
from app.extensions import csrf
from app.extensions import db


def _require_professional(user_id: str):
    user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
    user = User.query.get(user_uuid)
    if not user or not user.is_professional:
        abort(403)
    return user


@business_bp.get("/analytics")
@jwt_required()
def analytics_dashboard():
    user = _require_professional(get_jwt_identity())
    return render_template("business/analytics.html", user=user)


@business_bp.get("/analytics/data")
@jwt_required()
def analytics_data():
    user_id = get_jwt_identity()
    _require_professional(user_id)
    start_str = request.args.get("start")
    end_str = request.args.get("end")
    start = datetime.fromisoformat(start_str) if start_str else datetime.utcnow().replace(day=1)
    end = datetime.fromisoformat(end_str) if end_str else datetime.utcnow()
    data = get_insights(user_id, start, end)
    return jsonify(data)


@business_bp.get("/content")
@jwt_required()
def content():
    user_id = get_jwt_identity()
    _require_professional(user_id)
    return jsonify(content_analytics(user_id))


@business_bp.get("/ads")
@jwt_required()
def ads():
    user_id = get_jwt_identity()
    _require_professional(user_id)
    return jsonify(ads_performance(user_id))


@business_bp.get("/ads/latest")
@jwt_required()
def latest_campaign():
    user_id = get_jwt_identity()
    _require_professional(user_id)
    user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
    campaign = (
        AdCampaign.query.filter_by(creator_id=user_uuid)
        .order_by(AdCampaign.created_at.desc())
        .first()
    )
    if not campaign:
        return jsonify({}), 200
    txn = None
    if campaign.razorpay_order_id:
        txn = PaymentTransaction.query.filter_by(razorpay_order_id=campaign.razorpay_order_id).first()
    display_status = "paid" if (campaign.status == "paid" or (txn and txn.status == "paid")) else campaign.status
    days = max(1, (campaign.end_date.date() - campaign.start_date.date()).days + 1)
    daily_budget = int(campaign.budget / days) if campaign.budget else 0
    return jsonify(
        {
            "id": str(campaign.id),
            "name": campaign.name,
            "budget": campaign.budget,
            "daily_budget": daily_budget,
            "days": days,
            "start_date": campaign.start_date.date().isoformat(),
            "end_date": campaign.end_date.date().isoformat(),
            "order_id": campaign.razorpay_order_id,
            "status": campaign.status,
            "display_status": display_status,
        }
    )


@business_bp.get("/ads/list")
@jwt_required()
def list_campaigns():
    user_id = get_jwt_identity()
    _require_professional(user_id)
    user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
    campaigns = (
        AdCampaign.query.filter_by(creator_id=user_uuid)
        .order_by(AdCampaign.created_at.desc())
        .limit(20)
        .all()
    )
    order_ids = [c.razorpay_order_id for c in campaigns if c.razorpay_order_id]
    txn_map = {}
    if order_ids:
        txns = PaymentTransaction.query.filter(PaymentTransaction.razorpay_order_id.in_(order_ids)).all()
        txn_map = {t.razorpay_order_id: t for t in txns}
    data = []
    for c in campaigns:
        days = max(1, (c.end_date.date() - c.start_date.date()).days + 1)
        daily_budget = int(c.budget / days) if c.budget else 0
        txn = txn_map.get(c.razorpay_order_id)
        display_status = "paid" if (c.status == "paid" or (txn and txn.status == "paid")) else c.status
        data.append(
            {
                "id": str(c.id),
                "name": c.name,
                "budget": c.budget,
                "daily_budget": daily_budget,
                "days": days,
                "start_date": c.start_date.date().isoformat(),
                "end_date": c.end_date.date().isoformat(),
                "order_id": c.razorpay_order_id,
                "status": c.status,
                "display_status": display_status,
                "created_at": c.created_at.isoformat() if hasattr(c, "created_at") and c.created_at else None,
            }
        )
    return jsonify(data)


@business_bp.route("/ads/callback", methods=["GET", "POST"])
@csrf.exempt
@jwt_required(optional=True)
def ads_callback():
    payload = request.values
    rp_order_id = payload.get("razorpay_order_id")
    rp_payment_id = payload.get("razorpay_payment_id")
    rp_signature = payload.get("razorpay_signature")
    status = "error"
    message = None
    if not rp_order_id:
        message = "Missing Razorpay order id."
        return render_template("business/ads_payment_result.html", status=status, message=message, order_id=rp_order_id)

    # Update transaction and campaign if payment details are present; treat presence of payment_id as success
    if rp_payment_id:
        status = "success"
        message = None
        txn = PaymentTransaction.query.filter_by(razorpay_order_id=rp_order_id).first()
        if txn:
            txn.status = "paid"
            txn.razorpay_payment_id = rp_payment_id
            txn.razorpay_signature = rp_signature
        campaign = AdCampaign.query.filter_by(razorpay_order_id=rp_order_id).first()
        if campaign:
            campaign.status = "paid"
        db.session.commit()
    else:
        message = "Payment not completed."

    return render_template("business/ads_payment_result.html", status=status, message=message, order_id=rp_order_id)


@business_bp.post("/ads/campaign")
@jwt_required()
def create_campaign():
    user_id = get_jwt_identity()
    _require_professional(user_id)
    user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
    data = request.get_json(force=True)
    post_uuid = data.get("post_id")
    if post_uuid:
        post_uuid = post_uuid if isinstance(post_uuid, uuid.UUID) else uuid.UUID(str(post_uuid))
    start_date = datetime.fromisoformat(data.get("start_date"))
    end_date = datetime.fromisoformat(data.get("end_date"))
    days = max(1, (end_date.date() - start_date.date()).days + 1)
    daily_budget_rupees = max(100, int(data.get("budget", 0)))
    total_budget_rupees = daily_budget_rupees * days
    amount_paise = total_budget_rupees * 100

    campaign = AdCampaign(
        creator_id=user_uuid,
        post_id=post_uuid,
        name=data.get("name"),
        budget=total_budget_rupees,
        start_date=start_date,
        end_date=end_date,
        target_audience=data.get("target_audience", {}),
        visibility_score_boost=0.2,
        status="pending",
    )
    from app.extensions import db

    db.session.add(campaign)
    db.session.flush()
    # Razorpay receipt must be <= 40 chars; compress the UUID to avoid errors.
    short_receipt = f"cmp-{str(campaign.id)[:24]}"
    order = create_order_for_purpose(
        amount_paise,
        {
            "purpose": "boost_campaign",
            "campaign_id": str(campaign.id),
            "buyer_id": str(user_id),
            "days": days,
            "daily_budget_rupees": daily_budget_rupees,
            "total_budget_rupees": total_budget_rupees,
        },
        receipt=short_receipt,
    )
    campaign.razorpay_order_id = order["id"]
    db.session.commit()
    return jsonify({"campaign_id": str(campaign.id), "order": order})
