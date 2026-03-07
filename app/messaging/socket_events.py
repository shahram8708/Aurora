from functools import wraps
from flask import request, current_app
from flask_jwt_extended import decode_token
from flask_socketio import Namespace, emit, join_room, leave_room
from app.extensions import socketio, db
from app.models import Message
from .messaging_service import (
    save_message,
    mark_read,
    toggle_reaction,
    MessagingError,
    assert_membership,
)
from .redis_pubsub import channel_for_conversation, channel_for_user, publish_event

MESSAGE_NAMESPACE = "/ws/messages"
RATE_LIMIT_PER_MIN = 30


def _get_jwt_identity(token: str | None):
    if not token:
        return None
    try:
        decoded = decode_token(token)
        return decoded.get("sub") or decoded.get("identity")
    except Exception:
        return None


def _token_from_request():
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1]
    return request.args.get("token") or request.cookies.get("access_token_cookie")


def _rate_limit(user_id: str) -> bool:
    client = getattr(current_app, "redis_client", None)
    if not client:
        return False
    key = f"ratelimit:msg:{user_id}"
    count = client.incr(key)
    if count == 1:
        client.expire(key, 60)
    return count > RATE_LIMIT_PER_MIN


def authenticated(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = _token_from_request()
        identity = _get_jwt_identity(token)
        if not identity:
            return False  # disconnect
        request.user_id = str(identity)
        return f(*args, **kwargs)

    return wrapper


class MessageNamespace(Namespace):
    def on_connect(self):
        token = _token_from_request()
        identity = _get_jwt_identity(token)
        if not identity:
            return False
        request.user_id = str(identity)
        join_room(channel_for_user(request.user_id))
        emit("connected", {"user_id": request.user_id})

    def on_disconnect(self):
        pass

    @authenticated
    def on_join_conversation(self, data):
        conversation_id = data.get("conversation_id")
        assert_membership(conversation_id, request.user_id)
        join_room(channel_for_conversation(conversation_id))
        emit("joined", {"conversation_id": conversation_id})

    @authenticated
    def on_leave_conversation(self, data):
        conversation_id = data.get("conversation_id")
        leave_room(channel_for_conversation(conversation_id))

    @authenticated
    def on_send_message(self, data):
        current_app.logger.info(
            "socket send_message",
            extra={"conversation_id": data.get("conversation_id"), "user_id": request.user_id, "type": data.get("message_type")},
        )
        if _rate_limit(request.user_id):
            emit("error", {"message": "Rate limit exceeded"})
            return
        try:
            msg = save_message(
                data.get("conversation_id"),
                request.user_id,
                message_type=data.get("message_type"),
                content=data.get("content"),
                media_url=data.get("media_url"),
                media_mime=data.get("media_mime"),
                media_size=data.get("media_size"),
                duration_seconds=data.get("duration_seconds"),
                thumbnail_url=data.get("thumbnail_url"),
                reply_to_id=data.get("reply_to_id"),
                is_vanish=bool(data.get("is_vanish")),
                gif_provider=data.get("gif_provider"),
                gif_id=data.get("gif_id"),
                autoplay=bool(data.get("autoplay", True)),
            )
            payload = serialize_message(msg)
            room = channel_for_conversation(msg.conversation_id)
            socketio.emit("message", payload, room=room, namespace=MESSAGE_NAMESPACE)
            # Ensure sender always receives even if not yet joined the room
            emit("message", payload)
            publish_event(room, payload)
            publish_event(channel_for_user(request.user_id), payload)
            try:
                from app.notifications.notification_service import notify_dm_message

                notify_dm_message(msg, request.user_id)
            except Exception:
                current_app.logger.exception("Failed to enqueue DM notification")
            current_app.logger.info("socket send_message success", extra={"message_id": str(msg.id)})
        except MessagingError as exc:
            current_app.logger.warning(
                "socket send_message failed", extra={"reason": str(exc), "conversation_id": data.get("conversation_id")}
            )
            emit("error", {"message": str(exc)})
        except Exception:
            current_app.logger.exception("socket send_message exception")
            db.session.rollback()
            emit("error", {"message": "Failed to send"})

    @authenticated
    def on_mark_read(self, data):
        conversation_id = data.get("conversation_id")
        mark_read(conversation_id, request.user_id)
        payload = {"conversation_id": conversation_id, "user_id": request.user_id, "event": "read"}
        room = channel_for_conversation(conversation_id)
        socketio.emit("read_receipt", payload, room=room, namespace=MESSAGE_NAMESPACE)
        publish_event(room, payload)

    @authenticated
    def on_react(self, data):
        try:
            reaction = toggle_reaction(data.get("message_id"), request.user_id, data.get("reaction_type"))
            payload = {
                "message_id": data.get("message_id"),
                "user_id": request.user_id,
                "reaction_type": reaction.reaction_type if reaction else None,
            }
            msg = Message.query.get(data.get("message_id"))
            if not msg:
                return
            room = channel_for_conversation(msg.conversation_id)
            socketio.emit("reaction", payload, room=room, namespace=MESSAGE_NAMESPACE)
            publish_event(room, payload)
        except MessagingError as exc:
            emit("error", {"message": str(exc)})


def serialize_message(msg: Message) -> dict:
    return {
        "id": str(msg.id),
        "conversation_id": str(msg.conversation_id),
        "sender_id": str(msg.sender_id),
        "sender_username": getattr(msg.sender, "username", None),
        "sender_name": getattr(msg.sender, "name", None),
        "message_type": msg.message_type,
        "content": msg.content,
        "media_url": msg.media_url,
        "media_mime_type": msg.media_mime_type,
        "media_size_bytes": msg.media_size_bytes,
        "duration_seconds": msg.duration_seconds,
        "thumbnail_url": msg.thumbnail_url,
        "reply_to_id": str(msg.reply_to_id) if msg.reply_to_id else None,
        "is_vanish": msg.is_vanish,
        "is_deleted": msg.is_deleted,
        "gif_provider": msg.gif_provider,
        "gif_id": msg.gif_id,
        "autoplay": msg.autoplay,
        "created_at": msg.created_at.isoformat(),
    }


socketio.on_namespace(MessageNamespace(MESSAGE_NAMESPACE))
