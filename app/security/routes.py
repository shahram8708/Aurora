from datetime import datetime, timedelta
import json
import uuid
from flask import request, jsonify, current_app
from flask_jwt_extended import jwt_required
from app.extensions import db
from app.models import (
    User,
    LoginSession,
    EnforcementStrike,
    EnforcementAppeal,
    UserSetting,
)
from . import security_bp
from .rbac_service import require_roles, ensure_admin
from .validation import verify_webhook_signature


@security_bp.route("/dm-filter", methods=["POST"])
@jwt_required()
def update_dm_filter():
    payload = request.get_json() or {}
    keywords = payload.get("keywords", [])
    suspicious_links = payload.get("suspicious_links", True)
    shadow_ban = payload.get("shadow_ban", False)
    user_id = payload.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    key = f"dm_filter:{user_id}"
    data = json.dumps({"keywords": keywords, "suspicious_links": suspicious_links, "shadow_ban": shadow_ban})
    current_app.redis_client.set(key, data)
    return jsonify({"status": "updated"})


@security_bp.route("/comment-filter", methods=["POST"])
@jwt_required()
def update_comment_filter():
    payload = request.get_json() or {}
    user_id = payload.get("user_id")
    global_keywords = payload.get("global_keywords", [])
    blocked_keywords = payload.get("blocked_keywords", [])
    auto_hide = payload.get("auto_hide", True)
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    key = f"comment_filter:{user_id}"
    current_app.redis_client.set(key, json.dumps({"global": global_keywords, "blocked": blocked_keywords, "auto_hide": auto_hide}))
    return jsonify({"status": "updated"})


@security_bp.route("/age-restriction", methods=["POST"])
@jwt_required()
def enforce_age():
    payload = request.get_json() or {}
    user_id = payload.get("user_id")
    age = payload.get("age")
    if age is None or user_id is None:
        return jsonify({"error": "user_id and age required"}), 400
    if age < current_app.config["AGE_MINIMUM"]:
        user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
        user = User.query.get(user_uuid)
        if user:
            user.is_active = False
            db.session.commit()
        return jsonify({"status": "suspended", "reason": "age_restriction"}), 200
    return jsonify({"status": "ok"})


@security_bp.route("/parental/link", methods=["POST"])
@jwt_required()
def link_parent_child():
    payload = request.get_json() or {}
    child_id = payload.get("child_id")
    parent_id = payload.get("parent_id")
    if not child_id or not parent_id:
        return jsonify({"error": "child_id and parent_id required"}), 400
    setting = UserSetting.query.filter_by(user_id=child_id).first()
    if not setting:
        setting = UserSetting(user_id=child_id)
        db.session.add(setting)
    setting.parent_account_id = parent_id
    setting.restricted_mode = True
    setting.screen_time_limit_minutes = current_app.config["PARENTAL_SCREEN_TIME_LIMIT_DEFAULT"]
    db.session.commit()
    return jsonify({"status": "linked"})


@security_bp.route("/strike", methods=["POST"])
@jwt_required()
@ensure_admin
def issue_strike():
    payload = request.get_json() or {}
    user_id = payload.get("user_id")
    reason = payload.get("reason", "policy_violation")
    severity = payload.get("severity", "medium")
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
    strike = EnforcementStrike(user_id=user_uuid, reason=reason, severity=severity)
    db.session.add(strike)
    user = User.query.get(user_uuid)
    if user:
        user.failed_attempts = 0
        if severity == "high":
            user.is_active = False
            user.is_deleted = True
        elif severity == "medium":
            user.locked_until = datetime.utcnow() + timedelta(hours=24)
    db.session.commit()
    return jsonify({"strike_id": str(strike.id)})


@security_bp.route("/appeals", methods=["POST"])
@jwt_required()
def submit_appeal():
    payload = request.get_json() or {}
    strike_id = payload.get("strike_id")
    user_id = payload.get("user_id")
    notes = payload.get("notes")
    if not strike_id or not user_id:
        return jsonify({"error": "strike_id and user_id required"}), 400
    appeal = EnforcementAppeal(strike_id=strike_id, user_id=user_id, notes=notes)
    db.session.add(appeal)
    db.session.commit()
    return jsonify({"appeal_id": str(appeal.id), "status": "pending"})


@security_bp.route("/sessions/<uuid:user_id>", methods=["GET"])
@jwt_required()
def list_sessions(user_id):
    sessions = LoginSession.query.filter_by(user_id=user_id).order_by(LoginSession.last_seen_at.desc()).limit(20).all()
    return jsonify([
        {
            "id": str(s.id),
            "ip": s.ip_address,
            "user_agent": s.user_agent,
            "active": s.is_active,
            "last_seen_at": s.last_seen_at.isoformat(),
        }
        for s in sessions
    ])


@security_bp.route("/sessions/<uuid:session_id>", methods=["DELETE"])
@jwt_required()
def revoke_session(session_id):
    session = LoginSession.query.filter_by(id=session_id).first()
    if not session:
        return jsonify({"error": "not_found"}), 404
    session.is_active = False
    db.session.commit()
    return jsonify({"status": "revoked"})


@security_bp.route("/validate-webhook", methods=["POST"])
def validate_webhook():
    signature = request.headers.get("X-Razorpay-Signature")
    body = request.get_data()
    if not verify_webhook_signature(body, signature):
        return jsonify({"valid": False}), 400
    return jsonify({"valid": True})
