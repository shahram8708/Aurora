from flask import request, jsonify
from . import commerce_bp
from .razorpay_checkout_service import handle_webhook


@commerce_bp.post("/webhook/razorpay")
def razorpay_webhook():
    signature = request.headers.get("X-Razorpay-Signature")
    payload = request.get_json(force=True)
    body = request.get_data()
    handle_webhook(payload, signature, body)
    return jsonify({"status": "ok"})
