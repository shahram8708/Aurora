from datetime import datetime
from app.extensions import db
from app.models import CopyrightReport, EnforcementStrike


def mark_copyright_resolved(report_id: str, notes: str | None = None):
    report = CopyrightReport.query.filter_by(id=report_id).first()
    if not report:
        return None
    report.status = "resolved"
    report.notes = notes
    db.session.commit()
    return report


def add_copyright_strike(user_id, reason: str):
    strike = EnforcementStrike(user_id=user_id, reason=reason, severity="high")
    db.session.add(strike)
    db.session.commit()
    return strike


def escalate_repeat_offender(report_id: str):
    report = CopyrightReport.query.filter_by(id=report_id).first()
    if not report:
        return None
    report.strikes += 1
    if report.strikes >= 3:
        report.repeat_offender = True
    db.session.commit()
    return report


def takedown_content(report):
    # Placeholder for integration with content removal workflow
    report.status = "takedown"
    report.notes = f"Takedown issued at {datetime.utcnow().isoformat()}"
    db.session.commit()
    return report
