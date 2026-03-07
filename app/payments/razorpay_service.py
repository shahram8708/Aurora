import hmac
import hashlib
import uuid
import razorpay
from flask import current_app
from app.models import PaymentTransaction
from app.extensions import db


def razorpay_client() -> razorpay.Client:
    return razorpay.Client(auth=(current_app.config["RAZORPAY_KEY_ID"], current_app.config["RAZORPAY_KEY_SECRET"]))


def create_order_for_purpose(amount: int, notes: dict, receipt: str) -> dict:
    client = razorpay_client()
    order = client.order.create({"amount": amount, "currency": "INR", "receipt": receipt, "notes": notes, "payment_capture": 1})
    buyer = notes.get("buyer_id")
    buyer_uuid = None
    if buyer:
        try:
            buyer_uuid = buyer if isinstance(buyer, uuid.UUID) else uuid.UUID(str(buyer))
        except (ValueError, TypeError):
            buyer_uuid = None
    txn = PaymentTransaction(
        user_id=buyer_uuid,
        amount=amount,
        currency="INR",
        purpose=notes.get("purpose", "general"),
        status="created",
        razorpay_order_id=order["id"],
        metadata_json=notes,
    )
    db.session.add(txn)
    db.session.commit()
    return order


def capture_payment(payment_id: str, amount: int):
    client = razorpay_client()
    return client.payment.capture(payment_id, amount)


def refund_payment(payment_id: str, amount: int | None = None):
    client = razorpay_client()
    payload = {"amount": amount} if amount else {}
    return client.payment.refund(payment_id, payload)


def verify_signature(order_id: str, payment_id: str, signature: str):
    body = f"{order_id}|{payment_id}".encode()
    secret = current_app.config["RAZORPAY_KEY_SECRET"].encode()
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    if expected != signature:
        raise ValueError("Invalid signature")


def verify_webhook_signature(body: bytes, signature: str):
    secret = current_app.config["RAZORPAY_WEBHOOK_SECRET"].encode()
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    if expected != signature:
        raise ValueError("Invalid webhook signature")


def create_subscription_plan(amount: int, plan_id: str) -> dict:
    client = razorpay_client()
    return client.plan.create({"period": "monthly", "interval": 1, "item": {"name": f"creator-plan-{plan_id}", "amount": amount, "currency": "INR"}})


def create_subscription(plan_rp_id: str, subscriber_id: str, creator_id: str) -> dict:
    client = razorpay_client()
    return client.subscription.create(
        {
            "plan_id": plan_rp_id,
            "customer_notify": 1,
            "quantity": 1,
            # Razorpay requires at least one cycle; use 12 so we bill monthly for a year by default.
            "total_count": 12,
            "notes": {"subscriber_id": subscriber_id, "creator_id": creator_id},
        }
    )


def cancel_subscription(rp_subscription_id: str):
    client = razorpay_client()
    return client.subscription.cancel(rp_subscription_id)
