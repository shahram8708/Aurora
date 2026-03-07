import uuid
from functools import wraps
from datetime import datetime
from flask import request, current_app, url_for
from flask_jwt_extended import decode_token
from flask_socketio import Namespace, emit, join_room, leave_room
from app.extensions import socketio, db
from app.models import LiveSession, LiveParticipant, LiveModerationAction, User
from .live_service import add_comment, add_reaction, moderate_user, record_badge

LIVE_NAMESPACE = "/ws/live"


def _get_identity(token: str | None):
    if not token:
        return None
    try:
        decoded = decode_token(token)
        return str(decoded.get("sub") or decoded.get("identity"))
    except Exception:
        return None


def _token():
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1]
    return request.args.get("token") or request.cookies.get("access_token_cookie")


def _as_uuid(val):
    try:
        return uuid.UUID(str(val))
    except Exception:
        return None


def _rate_limit(user_id: str, session_id: str, window: int = 5, max_count: int = 10) -> bool:
    client = getattr(current_app, "redis_client", None)
    if not client:
        return False
    key = f"live:rate:{session_id}:{user_id}"
    count = client.incr(key)
    if count == 1:
        client.expire(key, window)
    return count > max_count


def authenticated(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        identity = _get_identity(_token())
        if not identity:
            return False
        request.user_id = identity
        return fn(*args, **kwargs)

    return wrapper


def _is_blocked(session_uuid, user_uuid) -> bool:
    if not session_uuid or not user_uuid:
        return False
    record = (
        LiveModerationAction.query.filter_by(session_id=session_uuid, target_id=user_uuid, action="block")
        .order_by(LiveModerationAction.created_at.desc())
        .first()
    )
    return record is not None


class LiveNamespace(Namespace):
    def on_connect(self):
        identity = _get_identity(_token())
        if not identity:
            return False
        request.user_id = identity
        emit("connected", {"user_id": identity})

    def on_disconnect(self):
        pass

    @authenticated
    def on_join(self, data):
        session_id = data.get("session_id")
        session_uuid = _as_uuid(session_id)
        user_uuid = _as_uuid(request.user_id)
        if not session_uuid:
            emit("error", {"message": "Invalid session."})
            return
        join_room(str(session_uuid))
        current_app.logger.info("live.join", extra={"session_id": session_id, "user_id": request.user_id})
        # track participant
        if session_uuid and user_uuid:
            if _is_blocked(session_uuid, user_uuid):
                emit("error", {"message": "You are blocked from this live and cannot join."})
                leave_room(str(session_uuid))
                return
            try:
                role = "viewer"
                session = LiveSession.query.get(session_uuid)
                if session and str(session.host_id) == str(user_uuid):
                    role = "host"
                db.session.merge(LiveParticipant(session_id=session_uuid, user_id=user_uuid, role=role))
                db.session.commit()
            except Exception as exc:
                current_app.logger.warning("live.join.participant.save_failed", exc_info=exc)
                db.session.rollback()
        emit("joined", {"session_id": str(session_uuid)})
        self._broadcast_presence(str(session_uuid))

    @authenticated
    def on_leave(self, data):
        session_id = data.get("session_id")
        session_uuid = _as_uuid(session_id)
        user_uuid = _as_uuid(request.user_id)
        current_app.logger.info("live.leave", extra={"session_id": session_id, "user_id": request.user_id})
        if session_uuid:
            leave_room(str(session_uuid))
        if session_uuid and user_uuid:
            try:
                LiveParticipant.query.filter_by(session_id=session_uuid, user_id=user_uuid).delete()
                db.session.commit()
            except Exception as exc:
                current_app.logger.warning("live.leave.participant.delete_failed", exc_info=exc)
                db.session.rollback()
        self._broadcast_presence(session_id if session_uuid else None)

    @authenticated
    def on_request_offer(self, data):
        session_id = data.get("session_id")
        current_app.logger.info("live.request_offer", extra={"session_id": session_id, "from_id": request.user_id})
        payload = {
            "session_id": session_id,
            "from_id": request.user_id,
        }
        socketio.emit("request-offer", payload, room=session_id, namespace=LIVE_NAMESPACE, skip_sid=request.sid)

    @authenticated
    def on_offer(self, data):
        session_id = data.get("session_id")
        current_app.logger.info("live.offer", extra={"session_id": session_id, "from_id": request.user_id, "target_id": data.get("target_id")})
        payload = {
            "session_id": session_id,
            "from_id": request.user_id,
            "target_id": data.get("target_id"),
            "sdp": data.get("sdp"),
        }
        socketio.emit("offer", payload, room=session_id, namespace=LIVE_NAMESPACE, skip_sid=request.sid)

    @authenticated
    def on_host_ready(self, data):
        session_id = data.get("session_id")
        current_app.logger.info("live.host_ready", extra={"session_id": session_id, "from_id": request.user_id})
        payload = {"session_id": session_id, "from_id": request.user_id}
        socketio.emit("host-ready", payload, room=session_id, namespace=LIVE_NAMESPACE, skip_sid=request.sid)

    @authenticated
    def on_answer(self, data):
        session_id = data.get("session_id")
        current_app.logger.info("live.answer", extra={"session_id": session_id, "from_id": request.user_id, "target_id": data.get("target_id")})
        payload = {
            "session_id": session_id,
            "from_id": request.user_id,
            "target_id": data.get("target_id"),
            "sdp": data.get("sdp"),
        }
        socketio.emit("answer", payload, room=session_id, namespace=LIVE_NAMESPACE, skip_sid=request.sid)

    @authenticated
    def on_ice_candidate(self, data):
        session_id = data.get("session_id")
        current_app.logger.info("live.ice", extra={"session_id": session_id, "from_id": request.user_id, "target_id": data.get("target_id")})
        payload = {
            "session_id": session_id,
            "from_id": request.user_id,
            "target_id": data.get("target_id"),
            "candidate": data.get("candidate"),
        }
        socketio.emit("ice-candidate", payload, room=session_id, namespace=LIVE_NAMESPACE, skip_sid=request.sid)

    @authenticated
    def on_comment(self, data):
        session_id = data.get("session_id")
        message = data.get("message")
        if _rate_limit(request.user_id, session_id):
            emit("error", {"message": "Rate limit"})
            return
        try:
            comment = add_comment(session_id, request.user_id, message)
            user = User.query.get(_as_uuid(request.user_id))
            username = user.username if user else str(request.user_id)
            payload = {
                "id": str(comment.id),
                "message": comment.message,
                "user_id": str(comment.user_id),
                "username": username,
                "profile_url": url_for("users.view_profile", user_id=str(comment.user_id)),
                "created_at": comment.created_at.isoformat(),
            }
            room = str(_as_uuid(session_id)) if _as_uuid(session_id) else session_id
            socketio.emit("comment", payload, room=room, namespace=LIVE_NAMESPACE)
        except Exception as exc:
            emit("error", {"message": str(exc)})

    @authenticated
    def on_reaction(self, data):
        session_id = data.get("session_id")
        reaction_type = data.get("reaction_type")
        reaction = add_reaction(session_id, request.user_id, reaction_type)
        payload = {
            "id": reaction.id,
            "user_id": request.user_id,
            "reaction_type": reaction.reaction_type,
            "created_at": reaction.created_at.isoformat(),
        }
        socketio.emit("reaction", payload, room=session_id, namespace=LIVE_NAMESPACE)

    @authenticated
    def on_badge(self, data):
        session_id = data.get("session_id")
        payment_id = data.get("razorpay_payment_id")
        order_id = data.get("razorpay_order_id")
        amount = int(data.get("amount"))
        txn = record_badge(session_id, request.user_id, amount, payment_id, order_id)
        payload = {
            "txn_id": txn.id,
            "amount": txn.amount,
            "sender_id": request.user_id,
            "created_at": txn.created_at.isoformat(),
        }
        socketio.emit("badge", payload, room=session_id, namespace=LIVE_NAMESPACE)

    @authenticated
    def on_moderate(self, data):
        session_id = data.get("session_id")
        target_id = data.get("target_id")
        action = data.get("action")
        result = moderate_user(session_id, request.user_id, target_id, action, reason=data.get("reason"))
        payload = {"action": result.get("action"), "target_id": target_id, "actor_id": request.user_id}
        socketio.emit("moderation", payload, room=session_id, namespace=LIVE_NAMESPACE)
        self._broadcast_presence(session_id)

    def _broadcast_presence(self, session_id: str):
        session_uuid = _as_uuid(session_id)
        if not session_uuid:
            return
        participants = (
            db.session.query(LiveParticipant.user_id, LiveParticipant.role, User.username, User.profile_photo_url)
            .join(User, User.id == LiveParticipant.user_id)
            .filter(LiveParticipant.session_id == session_uuid)
            .all()
        )
        payload = [
            {
                "user_id": str(u_id),
                "role": role,
                "username": username,
                "photo": profile_photo_url,
            }
            for (u_id, role, username, profile_photo_url) in participants
        ]
        socketio.emit("presence-update", {"session_id": session_id, "participants": payload}, room=session_id, namespace=LIVE_NAMESPACE)


socketio.on_namespace(LiveNamespace(LIVE_NAMESPACE))
