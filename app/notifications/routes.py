from datetime import datetime
from flask import jsonify, request, current_app, render_template
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import limiter
from . import notifications_bp
from .notification_service import (
    create_notification,
    list_notifications,
    mark_read,
    mark_all_read,
    delete_notifications,
    unread_count,
    register_device_token,
    NotificationError,
    _prefs,
)


@notifications_bp.get("/")
@jwt_required()
def list_notifs():
    user_id = get_jwt_identity()
    current_app.logger.info("list_notifications | user=%s", str(user_id))
    limit = int(request.args.get("limit", 30))
    before_str = request.args.get("before")
    before = datetime.fromisoformat(before_str) if before_str else None
    notifs = list_notifications(user_id, limit=limit, before=before)
    try:
        summary = [{"id": n.id, "type": n.type, "is_read": n.is_read, "ref": n.reference_id} for n in notifs]
        current_app.logger.info(
            "list_notifications_result | count=%s data=%s",
            len(notifs),
            summary,
        )
    except Exception as e:
        current_app.logger.warning("list_notifications_log_failed", exc_info=e)
    return jsonify([
        {
            "id": n.id,
            "actor_id": str(n.actor_id) if n.actor_id else None,
            "type": n.type,
            "reference_id": n.reference_id,
            "meta": n.meta or {},
            "is_read": n.is_read,
            "aggregated_count": n.aggregated_count,
            "created_at": n.created_at.isoformat(),
        }
        for n in notifs
    ])


@notifications_bp.get("/page")
@jwt_required()
def notifications_page():
    user_id = get_jwt_identity()
    notifs = list_notifications(user_id, limit=50)
    try:
        summary = [
            {
                "id": n.id,
                "type": n.type,
                "is_read": n.is_read,
                "ref": n.reference_id,
                "meta": n.meta,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notifs
        ]
        current_app.logger.info(
            "notifications_page_data | user=%s count=%s data=%s",
            str(user_id),
            len(notifs),
            summary,
        )
    except Exception as e:
        current_app.logger.warning("notifications_page_log_failed", exc_info=e)
    return render_template("notifications/list.html", notifications=notifs)


@notifications_bp.get("/unread-count")
@jwt_required()
def unread():
    user_id = get_jwt_identity()
    count = unread_count(user_id)
    current_app.logger.info("unread_count", extra={"user_id": user_id, "count": count})
    return jsonify({"unread": count})


@notifications_bp.post("/read")
@jwt_required()
def bulk_read():
    user_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}
    ids = data.get("ids", [])
    mark_all_read(user_id, ids or None)
    return jsonify({"status": "ok"})


@notifications_bp.post("/delete")
@jwt_required()
def bulk_delete():
    user_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}
    ids = data.get("ids", [])
    deleted = delete_notifications(user_id, ids or None)
    return jsonify({"deleted": deleted})


@notifications_bp.post("/delete-all")
@jwt_required()
def delete_all():
    user_id = get_jwt_identity()
    deleted = delete_notifications(user_id, None)
    return jsonify({"deleted": deleted})


@notifications_bp.post("/<int:nid>/delete")
@jwt_required()
def delete_single(nid):
    user_id = get_jwt_identity()
    deleted = delete_notifications(user_id, [nid])
    if not deleted:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"deleted": deleted})


@notifications_bp.post("/<int:nid>/read")
@jwt_required()
def single_read(nid):
    user_id = get_jwt_identity()
    try:
        notif = mark_read(nid, user_id)
        return jsonify({"id": notif.id, "is_read": notif.is_read})
    except NotificationError:
        return jsonify({"error": "Not found"}), 404


@notifications_bp.post("/device-token")
@jwt_required()
@limiter.limit("20/hour")
def register_device():
    user_id = get_jwt_identity()
    data = request.json or {}
    token = data.get("token")
    platform = data.get("platform", "ios")
    device_id = data.get("device_id")
    if not token:
        return jsonify({"error": "token required"}), 400
    register_device_token(user_id, token, platform, device_id)
    return jsonify({"status": "ok"})


@notifications_bp.get("/preferences")
@jwt_required()
def preferences():
    user_id = get_jwt_identity()
    prefs = _prefs(user_id)
    return jsonify(
        {
            "email_dm": prefs.email_dm,
            "email_follow": prefs.email_follow,
            "email_like": prefs.email_like,
            "email_comment": prefs.email_comment,
            "email_mention": prefs.email_mention,
            "email_live": prefs.email_live,
            "email_marketing": prefs.email_marketing,
            "email_security": prefs.email_security,
            "email_commerce": prefs.email_commerce,
            "push_enabled": prefs.push_enabled,
            "push_security": prefs.push_security,
            "push_commerce": prefs.push_commerce,
            "in_app_enabled": prefs.in_app_enabled,
            "quiet_hours_start": prefs.quiet_hours_start,
            "quiet_hours_end": prefs.quiet_hours_end,
            "unsubscribe_token": prefs.unsubscribe_token,
        }
    )


@notifications_bp.post("/preferences")
@jwt_required()
def update_preferences():
    user_id = get_jwt_identity()
    prefs = _prefs(user_id)
    data = request.json or {}
    for field in [
        "email_dm",
        "email_follow",
        "email_like",
        "email_comment",
        "email_mention",
        "email_live",
        "email_marketing",
        "email_security",
        "email_commerce",
        "push_enabled",
        "push_security",
        "push_commerce",
        "in_app_enabled",
        "quiet_hours_start",
        "quiet_hours_end",
    ]:
        if field in data:
            value = data[field]
            if field.startswith("quiet_hours"):
                try:
                    value = int(value) if value is not None else None
                except (TypeError, ValueError):
                    value = None
            else:
                value = bool(value)
            setattr(prefs, field, value)
    from app.extensions import db

    db.session.commit()
    return jsonify({"status": "ok"})


@notifications_bp.post("/test")
@jwt_required()
def test_send():
    user_id = get_jwt_identity()
    notif = create_notification(user_id, user_id, "dm", reference_id=None, metadata={"demo": True})
    return jsonify({"id": notif.id})
