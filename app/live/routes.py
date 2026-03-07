import uuid
from datetime import datetime
from flask import request, jsonify, abort, render_template, url_for, redirect, flash
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import limiter
from app.extensions import db, socketio
from app.models import LiveSession, LiveBadgeTransaction, LiveComment, LiveReaction, Follow, User, LiveParticipant, LiveModerationAction
from app.payments.razorpay_service import razorpay_client, create_order_for_purpose
from . import live_bp
LIVE_NAMESPACE = "/ws/live"
from .live_service import (
    schedule_live,
    start_session,
    end_session,
    add_comment,
    add_reaction,
    moderate_user,
    set_slow_mode,
    toggle_comments,
    pin_comment,
)



@live_bp.get("/create")
@jwt_required(optional=True)
def create_live_page():
    return render_template("live/create.html")


@live_bp.get("/browse")
@jwt_required(optional=True)
def browse_live():
    viewer_id = get_jwt_identity()
    sessions = []
    if viewer_id:
        try:
            viewer_uuid = uuid.UUID(str(viewer_id))
        except ValueError:
            viewer_uuid = None
        if viewer_uuid:
            follow_subq = db.session.query(Follow.following_id).filter(Follow.follower_id == viewer_uuid)
            sessions = (
                db.session.query(LiveSession, User)
                .join(User, LiveSession.host_id == User.id)
                .filter(LiveSession.is_active.is_(True))
                .filter((LiveSession.host_id == viewer_uuid) | (LiveSession.host_id.in_(follow_subq)))
                .order_by(LiveSession.started_at.desc())
                .all()
            )
    return render_template("live/browse.html", sessions=sessions)


@live_bp.get("/<uuid:session_id>")
@jwt_required(optional=True)
def view_live(session_id):
    session = LiveSession.query.get_or_404(session_id)
    from flask import current_app
    viewer_id = get_jwt_identity()
    if viewer_id:
        try:
            viewer_uuid = uuid.UUID(str(viewer_id))
        except Exception:
            viewer_uuid = None
        blocked = None
        if viewer_uuid:
            blocked = LiveModerationAction.query.filter_by(session_id=session_id, target_id=viewer_uuid, action="block").first()
        if blocked:
            flash("You are blocked from this live and cannot join.", "warning")
            return redirect(url_for("live.browse_live"))

    participants = (
        db.session.query(LiveParticipant.user_id, LiveParticipant.role, User.username, User.profile_photo_url)
        .join(User, User.id == LiveParticipant.user_id)
        .filter(LiveParticipant.session_id == session_id)
        .all()
    )
    participants_payload = [
        {
            "user_id": str(u_id),
            "role": role,
            "username": username,
            "photo": photo,
        }
        for (u_id, role, username, photo) in participants
    ]
    comments = (
        LiveComment.query.filter_by(session_id=session_id)
        .order_by(LiveComment.created_at.asc())
        .limit(200)
        .all()
    )
    comments_payload = [
        {
            "id": str(c.id),
            "message": c.message,
            "user_id": str(c.user_id),
            "username": (User.query.get(c.user_id).username if User.query.get(c.user_id) else str(c.user_id)),
            "created_at": c.created_at.isoformat(),
            "profile_url": url_for("users.view_profile", user_id=str(c.user_id)),
        }
        for c in comments
    ]
    return render_template(
        "live/session.html",
        session=session,
        razorpay_key=current_app.config.get("RAZORPAY_KEY_ID"),
        participants=participants_payload,
        comments=comments_payload,
    )


@live_bp.post("/schedule")
@jwt_required()
@limiter.limit("5 per hour")
def schedule():
    payload = request.get_json(force=True)
    scheduled_at = payload.get("scheduled_at")
    dt = datetime.fromisoformat(scheduled_at) if scheduled_at else None
    session = schedule_live(get_jwt_identity(), payload.get("title"), payload.get("description"), dt)
    return jsonify({"id": str(session.id), "stream_key": session.stream_key})


@live_bp.post("/<uuid:session_id>/start")
@jwt_required()
def start(session_id):
    session = start_session(session_id, get_jwt_identity())
    return jsonify({"id": str(session.id), "started_at": session.started_at.isoformat()})


@live_bp.post("/<uuid:session_id>/end")
@jwt_required()
def end(session_id):
    replay_url = request.json.get("replay_url") if request.is_json else None
    session = end_session(session_id, get_jwt_identity(), replay_url=replay_url)
    return jsonify({"id": str(session.id), "ended_at": session.ended_at.isoformat(), "replay_url": session.replay_url})


@live_bp.post("/<uuid:session_id>/comment")
@jwt_required()
def comment(session_id):
    message = request.json.get("message") if request.is_json else request.form.get("message")
    if not message:
        abort(400)
    user_id = get_jwt_identity()
    try:
        user_uuid = uuid.UUID(str(user_id))
    except Exception:
        abort(400)
    user = User.query.get(user_uuid)
    username = user.username if user else str(user_id)
    comment_obj = add_comment(session_id, user_id, message)
    payload = {
        "id": str(comment_obj.id),
        "message": comment_obj.message,
        "user_id": str(user_uuid),
        "username": username,
        "profile_url": url_for("users.view_profile", user_id=str(user_uuid)),
        "created_at": comment_obj.created_at.isoformat(),
    }
    # broadcast to live room so all viewers receive the comment
    socketio.emit("comment", payload, room=str(session_id), namespace=LIVE_NAMESPACE)
    return jsonify(payload)


@live_bp.post("/<uuid:session_id>/reaction")
@jwt_required()
def reaction(session_id):
    reaction_type = request.json.get("reaction_type") if request.is_json else request.form.get("reaction_type")
    reaction_obj = add_reaction(session_id, get_jwt_identity(), reaction_type)
    # broadcast so all viewers see the reaction bubble
    socketio.emit(
        "reaction",
        {"reaction_type": reaction_type},
        room=str(session_id),
        namespace=LIVE_NAMESPACE,
    )
    return jsonify({"id": str(reaction_obj.id)})


@live_bp.post("/<uuid:session_id>/moderate")
@jwt_required()
def moderate(session_id):
    data = request.get_json(force=True)
    action = data.get("action")
    target_id = data.get("target_id")
    result = moderate_user(session_id, get_jwt_identity(), target_id, action, reason=data.get("reason"))
    return jsonify({"id": result.get("id"), "action": result.get("action"), "target_id": result.get("target_id")})


@live_bp.post("/<uuid:session_id>/slowmode")
@jwt_required()
def slowmode(session_id):
    seconds = int(request.get_json(force=True).get("seconds", 0))
    set_slow_mode(session_id, seconds)
    return jsonify({"seconds": seconds})


@live_bp.post("/<uuid:session_id>/comments/toggle")
@jwt_required()
def toggle_commenting(session_id):
    enabled = bool(request.get_json(force=True).get("enabled", True))
    toggle_comments(session_id, enabled)
    return jsonify({"comments_enabled": enabled})


@live_bp.post("/<uuid:session_id>/comments/pin")
@jwt_required()
def pin(session_id):
    comment_id = int(request.get_json(force=True).get("comment_id"))
    pin_comment(comment_id, session_id, get_jwt_identity())
    return jsonify({"pinned": True})


@live_bp.get("/<uuid:session_id>/blocked")
@jwt_required()
def blocked_viewers(session_id):
    viewer_id = get_jwt_identity()
    session = LiveSession.query.get_or_404(session_id)
    if str(session.host_id) != str(viewer_id):
        abort(403)
    records = (
        LiveModerationAction.query.filter_by(session_id=session_id, action="block")
        .order_by(LiveModerationAction.created_at.desc())
        .all()
    )
    target_ids = [r.target_id for r in records]
    users = {str(u.id): u for u in User.query.filter(User.id.in_(target_ids)).all()} if target_ids else {}
    blocked = [
        {
            "user_id": str(r.target_id),
            "username": users.get(str(r.target_id)).username if users.get(str(r.target_id)) else str(r.target_id),
            "since": r.created_at.isoformat(),
        }
        for r in records
    ]
    return jsonify({"blocked": blocked})


@live_bp.post("/<uuid:session_id>/badge/order")
@jwt_required()
def create_badge_order(session_id):
    amount = int(request.get_json(force=True).get("amount"))
    notes = {"purpose": "live_badge", "session_id": str(session_id), "buyer_id": str(get_jwt_identity())}
    order = create_order_for_purpose(amount, notes, receipt=f"live-{session_id}-{uuid.uuid4().hex}")
    return jsonify(order)


@live_bp.get("/<uuid:session_id>/events")
@jwt_required()
def recent_events(session_id):
    comments = LiveComment.query.filter_by(session_id=session_id).order_by(LiveComment.created_at.desc()).limit(50)
    reactions = LiveReaction.query.filter_by(session_id=session_id).order_by(LiveReaction.created_at.desc()).limit(50)
    badges = LiveBadgeTransaction.query.filter_by(session_id=session_id).order_by(LiveBadgeTransaction.created_at.desc()).limit(50)
    return jsonify(
        {
            "comments": [c.message for c in comments],
            "reactions": [r.reaction_type for r in reactions],
            "badges": [b.amount for b in badges],
        }
    )
