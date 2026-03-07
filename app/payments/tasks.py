from app.extensions import celery, db
from app.models import PayoutRequest, CreatorWallet


@celery.task(name="app.payments.tasks.process_pending_payouts")
def process_pending_payouts():
    pending = PayoutRequest.query.filter_by(status="approved").all()
    for req in pending:
        # Integrate with actual payout provider here
        req.status = "processed"
        wallet = CreatorWallet.query.filter_by(user_id=req.user_id).first()
        if wallet:
            wallet.pending_payout = max(wallet.pending_payout - req.amount, 0)
    db.session.commit()
