from functools import wraps
from flask import request
from flask_jwt_extended import decode_token
from flask_socketio import Namespace, emit, join_room
from app.messaging.redis_pubsub import channel_for_user, publish_event
from app.notifications.notification_service import NOTIFICATION_NAMESPACE, serialize_notification
from app.models import Notification
from app.extensions import socketio


def _get_identity():
    token = _token_from_request()
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


def authenticated(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        identity = _get_identity()
        if not identity:
            return False
        request.user_id = str(identity)
        return fn(*args, **kwargs)

    return wrapper


class NotificationNamespace(Namespace):
    def on_connect(self):
        identity = _get_identity()
        if not identity:
            return False
        request.user_id = str(identity)
        join_room(channel_for_user(request.user_id))
        emit("connected", {"user_id": request.user_id})

    @authenticated
    def on_mark_read(self, data):
        nid = data.get("id")
        if not nid:
            return
        notif = Notification.query.filter_by(id=nid, recipient_id=request.user_id).first()
        if not notif:
            return
        notif.is_read = True
        from app.extensions import db

        db.session.commit()
        payload = serialize_notification(notif)
        publish_event(channel_for_user(request.user_id), payload)
        emit("notification", payload)


socketio.on_namespace(NotificationNamespace(NOTIFICATION_NAMESPACE))
