import hmac
import hashlib
from flask import current_app


def verify_webhook_signature(body: bytes, signature: str) -> bool:
    secret = current_app.config.get("RAZORPAY_WEBHOOK_SECRET", "")
    if not secret or not signature:
        return False
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)
