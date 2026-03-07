import logging
from datetime import datetime
from sqlalchemy import func
from app.extensions import db
from app.models import User, PaymentTransaction, LiveSession, ContentReport

metrics_logger = logging.getLogger("metrics")


def system_health():
    active_users = db.session.query(func.count(User.id)).filter(User.is_active.is_(True)).scalar()
    pending_reports = db.session.query(func.count(ContentReport.id)).filter(ContentReport.status == "pending").scalar()
    live_sessions = db.session.query(func.count(LiveSession.id)).filter(LiveSession.is_active.is_(True)).scalar()
    return {
        "active_users": active_users,
        "pending_reports": pending_reports,
        "live_sessions": live_sessions,
        "timestamp": datetime.utcnow().isoformat(),
    }


def record_metric(name: str, value):
    metrics_logger.info("METRIC %s %s", name, value)


def revenue_overview():
    total_revenue = db.session.query(func.sum(PaymentTransaction.amount)).scalar() or 0
    success = (
        db.session.query(func.sum(PaymentTransaction.amount))
        .filter(PaymentTransaction.status == "captured")
        .scalar()
        or 0
    )
    refunds = (
        db.session.query(func.count(PaymentTransaction.id))
        .filter(PaymentTransaction.status == "refunded")
        .scalar()
        or 0
    )
    return {"total": total_revenue, "successful": success, "refunds": refunds}
