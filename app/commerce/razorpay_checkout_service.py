import hmac
import hashlib
import razorpay
from flask import current_app
from app.extensions import db
from app.models import Order, PaymentTransaction


class RazorpayError(Exception):
    pass


def _client() -> razorpay.Client:
    return razorpay.Client(auth=(current_app.config["RAZORPAY_KEY_ID"], current_app.config["RAZORPAY_KEY_SECRET"]))


def create_gateway_order(order: Order) -> dict:
    client = _client()
    payload = {
        "amount": order.total_amount,
        "currency": order.currency,
        "receipt": str(order.id),
        "notes": {"order_id": str(order.id), "buyer_id": str(order.buyer_id)},
    }
    rp_order = client.order.create(payload)
    txn = PaymentTransaction(
        user_id=order.buyer_id,
        amount=order.total_amount,
        currency=order.currency,
        purpose="commerce-order",
        status="created",
        razorpay_order_id=rp_order["id"],
        metadata_json={"order_id": str(order.id)},
    )
    db.session.add(txn)
    db.session.flush()
    return rp_order


def verify_payment_signature(order_id: str, payment_id: str, signature: str):
    body = f"{order_id}|{payment_id}".encode()
    secret = current_app.config["RAZORPAY_KEY_SECRET"].encode()
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    if expected != signature:
        raise RazorpayError("Invalid signature")


def verify_webhook_signature(body: bytes, signature: str):
    secret = current_app.config["RAZORPAY_WEBHOOK_SECRET"].encode()
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    if expected != signature:
        raise RazorpayError("Invalid webhook signature")


def handle_webhook(payload: dict, signature: str, body: bytes):
    verify_webhook_signature(body, signature)
    event = payload.get("event")
    entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
    rp_order_id = entity.get("order_id")
    payment_id = entity.get("id")
    status = entity.get("status")
    order = Order.query.filter_by(razorpay_order_id=rp_order_id).first()
    if not order:
        return
    if event == "payment.captured" and status == "captured":
        order.status = "paid"
        order.razorpay_payment_id = payment_id
    elif event == "payment.failed":
        order.status = "failed"
    elif event.startswith("refund"):
        order.status = "refunded"
    db.session.commit()
