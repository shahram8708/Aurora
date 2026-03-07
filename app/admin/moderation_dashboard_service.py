from typing import Any, Dict, List
from sqlalchemy import func
from app.extensions import db
from app.models import ContentReport, UserReport, CopyrightReport


def fetch_reports(report_type: str, status: str | None = None, limit: int = 50) -> List[Dict[str, Any]]:
    model = {
        "content": ContentReport,
        "user": UserReport,
        "copyright": CopyrightReport,
    }.get(report_type)
    if not model:
        return []
    query = model.query
    if status:
        query = query.filter_by(status=status)
    records = query.order_by(model.created_at.desc()).limit(limit).all()
    return [serialize_report(r) for r in records]


def serialize_report(report):
    base = {"id": str(report.id), "status": report.status, "notes": getattr(report, "notes", None)}
    if isinstance(report, ContentReport):
        base.update(
            {
                "content_type": report.content_type,
                "content_id": report.content_id,
                "assigned_to": str(report.assigned_to) if report.assigned_to else None,
                "ai_result": report.ai_result,
            }
        )
    if isinstance(report, UserReport):
        base.update({"reported_user_id": str(report.reported_user_id)})
    if isinstance(report, CopyrightReport):
        base.update({"content_id": report.content_id, "proof_url": report.proof_url, "strikes": report.strikes})
    return base


def bulk_update_reports(report_ids: list[str], status: str, assigned_to=None):
    ContentReport.query.filter(ContentReport.id.in_(report_ids)).update({"status": status, "assigned_to": assigned_to}, synchronize_session=False)
    UserReport.query.filter(UserReport.id.in_(report_ids)).update({"status": status, "assigned_to": assigned_to}, synchronize_session=False)
    CopyrightReport.query.filter(CopyrightReport.id.in_(report_ids)).update({"status": status}, synchronize_session=False)
    db.session.commit()


def moderation_counts():
    return {
        "content": db.session.query(func.count(ContentReport.id)).scalar(),
        "user": db.session.query(func.count(UserReport.id)).scalar(),
        "copyright": db.session.query(func.count(CopyrightReport.id)).scalar(),
    }
