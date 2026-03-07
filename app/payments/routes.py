import json
from flask import request, jsonify, abort
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import limiter, db
from app.models import PaymentTransaction, AdCampaign
from . import payments_bp
from .razorpay_service import (
    create_order_for_purpose,
    verify_signature,
    verify_webhook_signature,
)
from .payout_service import request_payout
from app.live.live_service import record_badge
from app.monetization.monetization_service import record_affiliate_conversion, handle_subscription_webhook
from app.notifications.notification_dispatcher import dispatch_notification
from app.notifications.notification_service import NotificationError


@payments_bp.post("/order")
@jwt_required()
@limiter.limit("30 per hour")
def order():
    data = request.get_json(force=True)
    amount = int(data.get("amount"))
    purpose = data.get("purpose")
    notes = data.get("notes", {})
    notes.update({"purpose": purpose, "buyer_id": str(get_jwt_identity())})
    order_obj = create_order_for_purpose(amount, notes, receipt=data.get("receipt", purpose))
    return jsonify(order_obj)


@payments_bp.post("/capture")
@jwt_required()
def capture():
    payload = request.get_json(force=True)
    order_id = payload.get("order_id")
    payment_id = payload.get("payment_id")
    signature = payload.get("signature")
    verify_signature(order_id, payment_id, signature)
    txn = PaymentTransaction.query.filter_by(razorpay_order_id=order_id).first_or_404()
    txn.razorpay_payment_id = payment_id
    txn.razorpay_signature = signature
    txn.status = "paid"
    db.session.commit()
    _dispatch_payment(txn)
    return jsonify({"status": "ok"})


@payments_bp.post("/webhook")
@limiter.exempt
def webhook():
    signature = request.headers.get("X-Razorpay-Signature")
    body = request.get_data()
    try:
        verify_webhook_signature(body, signature)
    except Exception:
        abort(400)
    payload = request.get_json(force=True)
    event = payload.get("event")
    if event.startswith("subscription." ):
        handle_subscription_webhook(payload, signature, body)
        return jsonify({"status": "subscription-processed"})
    entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
    order_id = entity.get("order_id")
    payment_id = entity.get("id")
    txn = PaymentTransaction.query.filter_by(razorpay_order_id=order_id).first()
    if not txn:
        return jsonify({"status": "ignored"})
    txn.razorpay_payment_id = payment_id
    txn.status = "paid" if event.endswith("captured") else txn.status
    db.session.commit()
    _dispatch_payment(txn)
    return jsonify({"status": "processed"})


def _dispatch_payment(txn: PaymentTransaction):
    purpose = txn.purpose
    notes = txn.metadata_json or {}
    if purpose == "live_badge":
        record_badge(notes.get("session_id"), notes.get("buyer_id"), txn.amount, txn.razorpay_payment_id, txn.razorpay_order_id)
    elif purpose == "boost_campaign":
        campaign_id = notes.get("campaign_id")
        campaign = AdCampaign.query.get(campaign_id)
        if campaign:
            campaign.status = "active"
            campaign.budget = txn.amount
            db.session.commit()
    elif purpose == "affiliate_conversion":
        record_affiliate_conversion(notes.get("slug"), txn.amount)
    elif purpose == "subscription":
        pass

    try:
        dispatch_notification(
            recipient_id=str(txn.user_id),
            actor_id=None,
            ntype="payment_success" if txn.status == "paid" else "payment_failed",
            reference_id=txn.razorpay_order_id,
            metadata={"amount": txn.amount, "purpose": purpose, "payment_id": txn.razorpay_payment_id},
        )
    except NotificationError:
        pass


@payments_bp.post("/payouts")
@jwt_required()
def request_payout_route():
    data = request.get_json(force=True)
    payout = request_payout(get_jwt_identity(), int(data.get("amount")))
    return jsonify({"id": str(payout.id), "status": payout.status})
