import logging
from flask import jsonify, current_app
from app.extensions import db
from . import system_bp
from app.admin.monitoring_service import system_health

health_logger = logging.getLogger("metrics")


@system_bp.route("/healthz", methods=["GET"])
def healthz():
    stats = system_health()
    health_logger.info("HEALTH %s", stats)
    return jsonify({"status": "ok", **stats})


@system_bp.route("/metrics", methods=["GET"])
def metrics():
    stats = system_health()
    db_status = "ok"
    try:
        db.session.execute(db.text("SELECT 1"))
    except Exception:
        db_status = "degraded"
    return jsonify({"app": "social", "db": db_status, "stats": stats})


@system_bp.route("/rate-limit", methods=["GET"])
def rate_limit_config():
    limits = current_app.config.get("RATE_LIMIT_DEFAULT", "")
    admin_limit = current_app.config.get("RATE_LIMIT_ADMIN", "")
    return jsonify({"default": limits, "admin": admin_limit})
