import logging
from flask import g, request
from app.extensions import db
from app.models import AuditLog

security_logger = logging.getLogger("security")


def audit_admin_action(response):
    if not g.get("admin_user"):
        return response
    try:
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            action = f"{request.method} {request.path}"
            entry = AuditLog(
                actor_id=g.admin_user.id,
                action=action,
                target_type=request.view_args.get("target_type") if request.view_args else "endpoint",
                target_id=request.view_args.get("id") if request.view_args else None,
                metadata_json={"status_code": response.status_code},
                ip_address=request.remote_addr,
                user_agent=request.headers.get("User-Agent"),
            )
            db.session.add(entry)
            db.session.commit()
            security_logger.info("AUDIT %s %s", g.admin_user.id, action)
    except Exception:
        db.session.rollback()
    return response
