from flask import jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db, limiter
from app.models import User
from .moderation_service import moderation_service
from . import moderation_bp


@moderation_bp.route("/sensitive", methods=["POST"])
@jwt_required()
@limiter.limit("20 per minute")
def toggle_sensitive():
    user_id = get_jwt_identity()
    blur = bool(request.json.get("blur", True)) if request.is_json else True
    db.session.query(User).filter(User.id == user_id).update({User.blur_sensitive: blur})
    db.session.commit()
    return jsonify(blur_sensitive=blur)


@moderation_bp.route("/manual", methods=["POST"])
@jwt_required()
@limiter.limit("10 per minute")
def manual_flag():
    data = request.get_json(force=True)
    content_type = data.get("content_type")
    content_id = data.get("content_id")
    reason = data.get("reason", "manual")
    svc = moderation_service()
    evt = svc.mark_sensitive(content_type, content_id, reason)
    return jsonify(id=evt.id, flagged=evt.is_flagged)
