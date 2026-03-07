from datetime import datetime
from flask import current_app
from app.extensions import db
from app.models import CreatorWallet, PayoutRequest


class PayoutError(Exception):
    pass


def request_payout(user_id: str, amount: int) -> PayoutRequest:
    wallet = CreatorWallet.query.filter_by(user_id=user_id).first()
    if not wallet or wallet.available_balance < amount:
        raise PayoutError("Insufficient balance")
    if amount < current_app.config.get("MIN_PAYOUT_AMOUNT", 0):
        raise PayoutError("Below minimum withdrawal")
    wallet.available_balance -= amount
    wallet.pending_payout += amount
    request_obj = PayoutRequest(user_id=user_id, amount=amount, status="pending")
    db.session.add(request_obj)
    db.session.commit()
    return request_obj


def approve_payout(request_id: str):
    req = PayoutRequest.query.get_or_404(request_id)
    req.status = "approved"
    db.session.commit()
    return req


def mark_processed(request_id: str, reference_id: str):
    req = PayoutRequest.query.get_or_404(request_id)
    req.status = "processed"
    req.processed_at = datetime.utcnow()
    req.reference_id = reference_id
    wallet = CreatorWallet.query.filter_by(user_id=req.user_id).first()
    if wallet:
        wallet.pending_payout = max(wallet.pending_payout - req.amount, 0)
    db.session.commit()
    return req
