import os
import uuid
import requests
from datetime import datetime
from flask import request, jsonify, render_template, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func
from werkzeug.utils import secure_filename
from app.extensions import limiter
from app.core.storage import get_s3_client, s3_public_url
from app.models import User, DeviceSession, UserSetting
from . import messaging_bp
from .messaging_service import (
    get_or_create_direct_conversation,
    create_group_conversation,
    add_participants,
    remove_participant,
    save_message,
    fetch_messages,
    list_conversations,
    get_conversation_detail,
    MessagingError,
    accept_request,
    set_theme,
    mark_read,
    toggle_reaction,
    report_message,
)
from .socket_events import serialize_message
from .message_utils import validate_file, validate_voice, validate_video, sniff_mime


def _collect_identifiers(raw_value):
    if raw_value is None:
        return []
    if isinstance(raw_value, str):
        return [part.strip() for part in raw_value.split(',') if part and part.strip()]
    if isinstance(raw_value, list):
        parts = []
        for item in raw_value:
            if item is None:
                continue
            if isinstance(item, str):
                parts.append(item.strip())
            else:
                parts.append(str(item).strip())
        return [p for p in parts if p]
    return []


def _resolve_user_ids(raw_identifiers):
    identifiers = [i for i in raw_identifiers if i]
    if not identifiers:
        return []
    resolved = []
    missing = []
    for token in identifiers:
        try:
            resolved.append(str(uuid.UUID(token)))
            continue
        except Exception:
            pass
        user = User.query.filter(func.lower(User.username) == token.lower()).first()
        if not user:
            missing.append(token)
        else:
            resolved.append(str(user.id))
    if missing:
        raise MessagingError(f"User not found: {', '.join(missing)}")
    return resolved


def _conversation_meta(convo, viewer_id):
    """Build display-friendly metadata for a conversation."""
    other_user = None
    if not convo.is_group:
        other_user = next((p.user for p in convo.participants if str(p.user_id) != str(viewer_id)), None)
    display_name = convo.title or (other_user.name if other_user else ("Group" if convo.is_group else "Chat"))
    subtitle = (
        f"{len(convo.participants)} members"
        if convo.is_group
        else (f"@{other_user.username}" if other_user else "Direct chat")
    )
    members = [
        {
            "id": str(p.user_id),
            "name": p.user.name,
            "username": p.user.username,
            "role": p.role,
        }
        for p in convo.participants
        if p.user is not None
    ]

    last_active_at = None
    if other_user:
        settings = UserSetting.query.filter_by(user_id=other_user.id).first()
        show_activity = settings.show_activity if settings else True
        if show_activity:
            last_session = (
                DeviceSession.query.filter_by(user_id=other_user.id)
                .order_by(DeviceSession.last_active_at.desc())
                .first()
            )
            if last_session and last_session.last_active_at:
                last_active_at = last_session.last_active_at.isoformat()
    return {
        "display_name": display_name,
        "subtitle": subtitle,
        "member_count": len(convo.participants),
        "members": members,
        "avatar": convo.avatar_url,
        "other_user": other_user,
        "other_user_id": str(other_user.id) if other_user else None,
        "other_username": other_user.username if other_user else None,
        "last_active_at": last_active_at,
    }


@messaging_bp.get("/inbox")
@jwt_required()
def inbox():
    user_id = get_jwt_identity()
    convos = list_conversations(user_id)
    requests = [c for c in convos if any(p.user_id == user_id and p.is_request for p in c.participants)]
    inbox_items = [c for c in convos if c not in requests]
    convo_cards = [
        {"convo": c, "meta": _conversation_meta(c, user_id)}
        for c in inbox_items
    ]
    return render_template("messaging/inbox.html", convos=convo_cards, requests=requests)


@messaging_bp.get("/conversations/<uuid:conversation_id>/view")
@jwt_required()
def view_conversation(conversation_id):
    user_id = get_jwt_identity()
    convo = get_conversation_detail(conversation_id, user_id)
    meta = _conversation_meta(convo, user_id)
    convo_msgs = fetch_messages(conversation_id, user_id, limit=50)
    return render_template(
        "messaging/conversation.html",
        conversation_id=conversation_id,
        messages=convo_msgs,
        conversation_meta=meta,
    )


@messaging_bp.get("/requests")
@jwt_required()
def requests_page():
    user_id = get_jwt_identity()
    convos = list_conversations(user_id)
    requests = [c for c in convos if any(p.user_id == user_id and p.is_request for p in c.participants)]
    return render_template("messaging/requests.html", requests=requests)


@messaging_bp.get("/conversations")
@jwt_required()
def conversations():
    user_id = get_jwt_identity()
    convos = list_conversations(user_id)
    return jsonify([
        {
            "id": str(c.id),
            "is_group": c.is_group,
            "title": c.title,
            "theme": c.theme,
            "last_message_at": c.last_message_at.isoformat() if c.last_message_at else None,
            "participants": [
                {
                    "user_id": str(p.user_id),
                    "role": p.role,
                    "is_muted": p.is_muted,
                    "is_request": p.is_request,
                    "last_read_at": p.last_read_at.isoformat() if p.last_read_at else None,
                    "theme": p.theme,
                }
                for p in c.participants
            ],
        }
        for c in convos
    ])


@messaging_bp.post("/conversations/direct")
@jwt_required()
@limiter.limit("10/minute")
def direct_conversation():
    user_id = get_jwt_identity()
    payload = request.json or {}
    raw_username = (payload.get("username") or "").strip()
    other_id = payload.get("user_id")

    other_user = None
    if raw_username:
        other_user = User.query.filter(func.lower(User.username) == raw_username.lower()).first()
        if not other_user:
            return jsonify({"error": "User not found"}), 404
        other_id = str(other_user.id)
    if not other_id:
        return jsonify({"error": "Username is required"}), 400

    try:
        convo = get_or_create_direct_conversation(user_id, other_id)
        return jsonify({"conversation_id": str(convo.id)}), 201
    except MessagingError as exc:
        return jsonify({"error": str(exc)}), 400


@messaging_bp.post("/conversations/group")
@jwt_required()
@limiter.limit("5/minute")
def group_conversation():
    user_id = get_jwt_identity()
    payload = request.json or {}
    member_ids = _collect_identifiers(payload.get("member_ids")) + _collect_identifiers(payload.get("member_usernames"))
    title = payload.get("title")
    if not member_ids:
        return jsonify({"error": "At least one username or ID is required"}), 400
    try:
        resolved_ids = _resolve_user_ids(member_ids)
        convo = create_group_conversation(user_id, resolved_ids, title)
        return jsonify({"conversation_id": str(convo.id)}), 201
    except MessagingError as exc:
        return jsonify({"error": str(exc)}), 400


@messaging_bp.post("/conversations/<uuid:conversation_id>/participants")
@jwt_required()
def add_members(conversation_id):
    user_id = get_jwt_identity()
    payload = request.json or {}
    new_ids = _collect_identifiers(payload.get("user_ids")) + _collect_identifiers(payload.get("usernames"))
    if not new_ids:
        return jsonify({"error": "At least one username or ID is required"}), 400
    try:
        resolved = _resolve_user_ids(new_ids)
        add_participants(conversation_id, user_id, resolved)
        return jsonify({"status": "ok"})
    except MessagingError as exc:
        return jsonify({"error": str(exc)}), 400


@messaging_bp.delete("/conversations/<uuid:conversation_id>/participants/<uuid:target_id>")
@jwt_required()
def remove_member(conversation_id, target_id):
    user_id = get_jwt_identity()
    try:
        remove_participant(conversation_id, user_id, str(target_id))
        return jsonify({"status": "ok"})
    except MessagingError as exc:
        return jsonify({"error": str(exc)}), 400


@messaging_bp.post("/conversations/<uuid:conversation_id>/accept")
@jwt_required()
def accept(conversation_id):
    user_id = get_jwt_identity()
    accept_request(conversation_id, user_id)
    return jsonify({"status": "ok"})


@messaging_bp.post("/conversations/<uuid:conversation_id>/theme")
@jwt_required()
def update_theme(conversation_id):
    user_id = get_jwt_identity()
    theme = request.json.get("theme", "default")
    set_theme(conversation_id, user_id, theme)
    return jsonify({"status": "ok"})


@messaging_bp.get("/gifs")
@jwt_required()
def list_gifs():
    term = (request.args.get("q") or "").strip()
    key = current_app.config.get("TENOR_API_KEY", "LIVDSRZULELA")
    def fetch_v2(q_term: str | None):
        base_url = "https://tenor.googleapis.com/v2/search" if q_term else "https://tenor.googleapis.com/v2/featured"
        params = {
            "key": key,
            "client_key": "aurora-web",
            "limit": 24,
            "media_filter": "gif",
        }
        if q_term:
            params["q"] = q_term
        return requests.get(base_url, params=params, timeout=6)

    def fetch_v1(q_term: str | None):
        base_url = "https://g.tenor.com/v1/search" if q_term else "https://g.tenor.com/v1/trending"
        params = {
            "key": key,
            "limit": 24,
            "media_filter": "minimal",
        }
        if q_term:
            params["q"] = q_term
        return requests.get(base_url, params=params, timeout=6)

    def normalize_v1(results: list[dict]):
        norm = []
        for item in results or []:
            media = item.get("media") or []
            gif_url = None
            if media:
                tiny = media[0].get("tinygif") if isinstance(media[0], dict) else None
                gif = media[0].get("gif") if isinstance(media[0], dict) else None
                gif_url = (tiny or {}).get("url") or (gif or {}).get("url")
            if gif_url:
                norm.append({"media_formats": {"gif": {"url": gif_url}}})
        return norm

    try:
        resp = fetch_v2(term or None)
        if not resp.ok:
            current_app.logger.warning("tenor v2 failed", extra={"status": resp.status_code, "body": resp.text[:200]})
        else:
            data = resp.json()
            results = data.get("results") or []
            if results:
                return jsonify({"results": results}), 200

        # Fallback to v1
        resp_v1 = fetch_v1(term or None)
        if not resp_v1.ok:
            current_app.logger.warning("tenor v1 failed", extra={"status": resp_v1.status_code, "body": resp_v1.text[:200]})
            return jsonify({"results": []}), 200
        data_v1 = resp_v1.json()
        normalized = normalize_v1(data_v1.get("results") or [])
        return jsonify({"results": normalized}), 200
    except Exception:
        current_app.logger.warning("tenor fetch failed", exc_info=True)
        return jsonify({"results": []}), 200


def _file_size(uploaded):
    try:
        uploaded.stream.seek(0, os.SEEK_END)
        size = uploaded.stream.tell()
        uploaded.stream.seek(0)
        return size
    except Exception:  # pragma: no cover - fallback only
        return uploaded.content_length or 0


@messaging_bp.post("/attachments")
@jwt_required()
@limiter.limit("20/minute")
def upload_attachment():
    user_id = get_jwt_identity()
    uploaded = request.files.get("file")
    if not uploaded:
        return jsonify({"error": "No file provided"}), 400

    filename = secure_filename(uploaded.filename or "upload") or "upload"
    mime = uploaded.mimetype or sniff_mime(filename) or "application/octet-stream"
    size = uploaded.content_length or _file_size(uploaded)
    type_hint = (request.form.get("type") or "").lower()

    try:
        if type_hint == "voice" or mime.startswith("audio/"):
            validate_voice(filename, mime, size)
            message_type = "voice"
        elif type_hint == "video" or mime.startswith("video/"):
            validate_video(filename, mime, size)
            message_type = "video"
        elif mime.startswith("image/") and type_hint != "file":
            validate_file(filename, mime, size)
            message_type = "image"
        else:
            validate_file(filename, mime, size)
            message_type = "file"
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    key = f"messages/{user_id}/{uuid.uuid4().hex}_{filename}"
    try:
        client = get_s3_client()
        bucket = current_app.config.get("AWS_S3_BUCKET") or "local"
        uploaded.stream.seek(0)
        client.upload_fileobj(
            uploaded,
            bucket,
            key,
            ExtraArgs={"ContentType": mime, "ACL": "public-read"},
        )
    except Exception:
        current_app.logger.exception("Attachment upload failed")
        return jsonify({"error": "Upload failed"}), 500

    return jsonify(
        {
            "media_url": s3_public_url(key),
            "media_mime": mime,
            "media_size": size,
            "message_type": message_type,
        }
    )


@messaging_bp.post("/messages")
@jwt_required()
@limiter.limit("30/minute")
def send_message():
    user_id = get_jwt_identity()
    data = request.json or {}
    current_app.logger.info(
        "/messaging/messages send",
        extra={"conversation_id": data.get("conversation_id"), "user_id": user_id, "type": data.get("message_type")},
    )
    try:
        msg = save_message(
            data.get("conversation_id"),
            user_id,
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
        current_app.logger.info(
            "/messaging/messages send success",
            extra={"message_id": str(msg.id), "conversation_id": msg.conversation_id},
        )
        return jsonify(serialize_message(msg)), 201
    except MessagingError as exc:
        current_app.logger.warning("/messaging/messages failed", extra={"reason": str(exc)})
        return jsonify({"error": str(exc)}), 400
    except Exception:
        current_app.logger.exception("/messaging/messages exception")
        return jsonify({"error": "Failed to send"}), 500


@messaging_bp.get("/conversations/<uuid:conversation_id>/messages")
@jwt_required()
def conversation_messages(conversation_id):
    user_id = get_jwt_identity()
    limit = int(request.args.get("limit", 30))
    before_str = request.args.get("before")
    before = datetime.fromisoformat(before_str) if before_str else None
    msgs = fetch_messages(conversation_id, user_id, limit=limit, before=before)
    return jsonify([serialize_message(m) for m in msgs])


@messaging_bp.post("/conversations/<uuid:conversation_id>/read")
@jwt_required()
def read(conversation_id):
    user_id = get_jwt_identity()
    mark_read(conversation_id, user_id)
    return jsonify({"status": "ok"})


@messaging_bp.post("/messages/<uuid:message_id>/react")
@jwt_required()
def react(message_id):
    user_id = get_jwt_identity()
    data = request.json or {}
    reaction = toggle_reaction(message_id, user_id, data.get("reaction_type"))
    return jsonify({"reaction_type": reaction.reaction_type if reaction else None})


@messaging_bp.post("/messages/<uuid:message_id>/report")
@jwt_required()
def report(message_id):
    user_id = get_jwt_identity()
    data = request.json or {}
    report = report_message(message_id, user_id, data.get("reason", ""))
    return jsonify({"report_id": report.id})
