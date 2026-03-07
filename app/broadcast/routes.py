from datetime import datetime
from flask import request, jsonify, render_template, flash, redirect, url_for, abort, g
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import limiter
from app.models import BroadcastChannel, User
from . import broadcast_bp
from .services import (
    create_channel,
    subscribe,
    unsubscribe,
    create_broadcast,
    mark_sent,
    track_open,
    channel_open_rate,
    list_channel_messages,
    channel_subscribers,
    list_user_channels,
    list_all_channels,
    BroadcastError,
)
from app.notifications.notification_service import create_notification, NotificationError


@broadcast_bp.post("/channels")
@jwt_required()
@limiter.limit("5/minute")
def create_channel_route():
    user_id = get_jwt_identity()
    data = request.json or {}
    try:
        channel = create_channel(user_id, data.get("name", "Untitled"), data.get("description"))
        return jsonify({"id": str(channel.id)}), 201
    except Exception as exc:  # pylint: disable=broad-except
        return jsonify({"error": str(exc)}), 400


@broadcast_bp.get("/channels")
@jwt_required()
def list_channels_route():
    user_id = get_jwt_identity()
    channels = list_user_channels(user_id)
    return jsonify(
        [
            {
                "id": str(c.id),
                "name": c.name,
                "description": c.description,
                "created_by": str(c.created_by),
                "is_owner": str(c.created_by) == str(user_id),
            }
            for c in channels
        ]
    )


@broadcast_bp.get("/channels/all")
@jwt_required()
def list_all_channels_route():
    user_id = get_jwt_identity()
    channels = list_all_channels(user_id)
    return jsonify(
        [
            {
                "id": str(c["channel"].id),
                "name": c["channel"].name,
                "description": c["channel"].description,
                "created_by": str(c["channel"].created_by),
                "is_owner": c["is_owner"],
                "is_subscribed": c["is_subscribed"],
                "subscriber_count": c["subscriber_count"],
            }
            for c in channels
        ]
    )


@broadcast_bp.post("/channels/<uuid:channel_id>/subscribe")
@jwt_required()
def subscribe_route(channel_id):
    user_id = get_jwt_identity()
    subscribe(channel_id, user_id)
    return jsonify({"status": "ok"})


@broadcast_bp.post("/channels/<uuid:channel_id>/unsubscribe")
@jwt_required()
def unsubscribe_route(channel_id):
    user_id = get_jwt_identity()
    unsubscribe(channel_id, user_id)
    return jsonify({"status": "ok"})


@broadcast_bp.post("/channels/<uuid:channel_id>/messages")
@jwt_required()
@limiter.limit("10/minute")
def create_broadcast_route(channel_id):
    user_id = get_jwt_identity()
    data = request.json or {}
    scheduled_at = data.get("scheduled_at")
    dt = datetime.fromisoformat(scheduled_at) if scheduled_at else None
    try:
        msg = create_broadcast(channel_id, user_id, data.get("content", ""), scheduled_at=dt)
        # notify subscribers
        for sub in channel_subscribers(channel_id):
            if str(sub.user_id) == user_id:
                continue
            try:
                create_notification(
                    str(sub.user_id),
                    user_id,
                    "dm",
                    reference_id=str(msg.id),
                    metadata={"channel_id": str(channel_id)},
                )
            except NotificationError:
                continue
        return jsonify({"id": str(msg.id)}), 201
    except BroadcastError as exc:
        return jsonify({"error": str(exc)}), 400


@broadcast_bp.post("/messages/<uuid:message_id>/sent")
@jwt_required()
def mark_sent_route(message_id):
    mark_sent(message_id)
    return jsonify({"status": "ok"})


@broadcast_bp.post("/messages/<uuid:message_id>/open")
@jwt_required()
def open_route(message_id):
    user_id = get_jwt_identity()
    track_open(message_id, user_id)
    return jsonify({"status": "ok"})


@broadcast_bp.get("/channels/<uuid:channel_id>/open-rate")
@jwt_required()
def open_rate_route(channel_id):
    return jsonify({"open_rate": channel_open_rate(channel_id)})


@broadcast_bp.get("/channels/<uuid:channel_id>/messages")
@jwt_required()
def list_messages(channel_id):
    msgs = list_channel_messages(channel_id)
    return jsonify(
        [
            {
                "id": str(m.id),
                "content": m.content,
                "scheduled_at": m.scheduled_at.isoformat() if m.scheduled_at else None,
                "sent_at": m.sent_at.isoformat() if m.sent_at else None,
                "created_at": m.created_at.isoformat(),
            }
            for m in msgs
        ]
    )


@broadcast_bp.get("/channels/<uuid:channel_id>/subscribers")
@jwt_required()
def list_subs(channel_id):
    subs = channel_subscribers(channel_id)
    return jsonify([{"user_id": str(s.user_id), "joined_at": s.joined_at.isoformat()} for s in subs])


@broadcast_bp.get("/")
def broadcast_dashboard():
    user = getattr(g, "current_user", None)
    if not user or not user.is_authenticated:
        return redirect(url_for("auth.login"))
    user_id = str(user.id)
    channels = list_all_channels(user_id)
    owned_channels = [c for c in channels if c["is_owner"]]
    subscribed_channels = [c for c in channels if c["is_subscribed"] and not c["is_owner"]]
    owner_ids = {c["channel"].created_by for c in channels}
    user_map = {u.id: u for u in User.query.filter(User.id.in_(owner_ids)).all()} if owner_ids else {}
    return render_template(
        "broadcast/dashboard.html",
        owned_channels=owned_channels,
        subscribed_channels=subscribed_channels,
        all_channels=channels,
        user_map=user_map,
    )


@broadcast_bp.post("/channels/create/html")
def create_channel_form_route():
    user = getattr(g, "current_user", None)
    if not user or not user.is_authenticated:
        return redirect(url_for("auth.login"))
    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip() or None
    if not name:
        flash("Channel name is required", "danger")
        return redirect(url_for("broadcast.broadcast_dashboard"))
    try:
        channel = create_channel(str(user.id), name, description)
        flash("Channel created", "success")
        return redirect(url_for("broadcast.channel_detail_page", channel_id=channel.id))
    except BroadcastError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("broadcast.broadcast_dashboard"))


@broadcast_bp.post("/channels/<uuid:channel_id>/subscribe/html")
def subscribe_html(channel_id):
    user = getattr(g, "current_user", None)
    if not user or not user.is_authenticated:
        return redirect(url_for("auth.login"))
    try:
        subscribe(channel_id, str(user.id))
        flash("Subscribed to channel", "success")
    except BroadcastError as exc:
        flash(str(exc), "danger")
    return redirect(request.referrer or url_for("broadcast.broadcast_dashboard"))


@broadcast_bp.post("/channels/<uuid:channel_id>/unsubscribe/html")
def unsubscribe_html(channel_id):
    user = getattr(g, "current_user", None)
    if not user or not user.is_authenticated:
        return redirect(url_for("auth.login"))
    try:
        unsubscribe(channel_id, str(user.id))
        flash("Unsubscribed", "info")
    except BroadcastError as exc:
        flash(str(exc), "danger")
    return redirect(request.referrer or url_for("broadcast.broadcast_dashboard"))


@broadcast_bp.get("/channels/<uuid:channel_id>/overview")
def channel_detail_page(channel_id):
    user = getattr(g, "current_user", None)
    if not user or not user.is_authenticated:
        return redirect(url_for("auth.login"))
    channel = BroadcastChannel.query.get(channel_id)
    if not channel:
        abort(404)

    user_id = str(user.id)
    subscribers = channel_subscribers(channel_id)
    audience_ids = {channel.created_by} | {s.user_id for s in subscribers}
    user_map = {u.id: u for u in User.query.filter(User.id.in_(audience_ids)).all()} if audience_ids else {}
    is_owner = str(channel.created_by) == user_id
    is_subscribed = any(str(sub.user_id) == user_id for sub in subscribers)
    messages = list_channel_messages(channel_id, limit=100)
    return render_template(
        "broadcast/channel_detail.html",
        channel=channel,
        subscribers=subscribers,
        subscriber_count=len(subscribers),
        is_owner=is_owner,
        is_subscribed=is_subscribed,
        messages=messages,
        open_rate=channel_open_rate(channel_id),
        user_map=user_map,
    )


@broadcast_bp.post("/channels/<uuid:channel_id>/message/create")
def create_broadcast_form_route(channel_id):
    user = getattr(g, "current_user", None)
    if not user or not user.is_authenticated:
        return redirect(url_for("auth.login"))
    content = (request.form.get("content") or "").strip()
    scheduled_at_raw = request.form.get("scheduled_at")
    scheduled_at = datetime.fromisoformat(scheduled_at_raw) if scheduled_at_raw else None

    if not content:
        flash("Message content is required", "danger")
        return redirect(url_for("broadcast.channel_detail_page", channel_id=channel_id))

    try:
        create_broadcast(channel_id, str(user.id), content, scheduled_at=scheduled_at)
        flash("Broadcast created", "success")
    except BroadcastError as exc:
        flash(str(exc), "danger")

    return redirect(url_for("broadcast.channel_detail_page", channel_id=channel_id))


@broadcast_bp.post("/messages/<uuid:message_id>/mark-sent")
def mark_sent_form_route(message_id):
    user = getattr(g, "current_user", None)
    if not user or not user.is_authenticated:
        return redirect(url_for("auth.login"))
    channel_id = request.form.get("channel_id")
    mark_sent(message_id)
    flash("Marked as sent", "info")
    if channel_id:
        return redirect(url_for("broadcast.channel_detail_page", channel_id=channel_id))
    return redirect(url_for("broadcast.broadcast_dashboard"))
