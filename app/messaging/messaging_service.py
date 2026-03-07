import html
from datetime import datetime
from typing import Iterable, Sequence
from sqlalchemy import and_, func
from sqlalchemy.orm import joinedload
import uuid
from app.extensions import db
from app.models import Conversation, ConversationParticipant, Message, MessageReaction, MessageReport, Follow, Block, Restrict, User, UserSetting
from .message_utils import validate_file, validate_voice, validate_video, validate_gif_url, validate_gif_provider


MAX_GROUP_MEMBERS = 50


class MessagingError(Exception):
    pass


def _is_blocked(user_id: str, other_id: str) -> bool:
    uid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
    oid = other_id if isinstance(other_id, uuid.UUID) else uuid.UUID(str(other_id))
    return (
        Block.query.filter_by(user_id=uid, target_id=oid).first() is not None
        or Block.query.filter_by(user_id=oid, target_id=uid).first() is not None
    )


def _is_restricted_by(receiver_id: str, sender_id: str) -> bool:
    """Return True when receiver has restricted the sender."""
    try:
        rid = receiver_id if isinstance(receiver_id, uuid.UUID) else uuid.UUID(str(receiver_id))
        sid = sender_id if isinstance(sender_id, uuid.UUID) else uuid.UUID(str(sender_id))
    except (TypeError, ValueError):
        return False
    return Restrict.query.filter_by(user_id=rid, target_id=sid).first() is not None


def get_or_create_direct_conversation(user_id: str, other_user_id: str) -> Conversation:
    uid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
    oid = other_user_id if isinstance(other_user_id, uuid.UUID) else uuid.UUID(str(other_user_id))
    if uid == oid:
        raise MessagingError("Cannot message yourself")
    if _is_blocked(user_id, other_user_id):
        raise MessagingError("User is blocked")
    other_user = User.query.get(oid)
    if not other_user or other_user.is_deleted or not other_user.is_active:
        raise MessagingError("User not available")
    existing = (
        Conversation.query.filter_by(is_group=False)
        .join(ConversationParticipant)
        .filter(ConversationParticipant.user_id.in_([uid, oid]))
        .group_by(Conversation.id)
        .having(func.count(ConversationParticipant.user_id.distinct()) == 2)
        .first()
    )
    if existing:
        return existing

    # DM privacy gate: enforce receiver preference before creating a new thread
    other_settings = UserSetting.query.filter_by(user_id=oid).first()
    # Default to open DMs when no settings row exists; otherwise honor user's preference.
    dm_policy = (other_settings.dm_privacy if other_settings else "everyone").lower()
    if dm_policy == "none":
        raise MessagingError("This user is not accepting new messages")
    if dm_policy == "followers":
        is_follower = Follow.query.filter(and_(Follow.follower_id == uid, Follow.following_id == oid)).first()
        if not is_follower:
            raise MessagingError("Only followers can message this user")

    convo = Conversation(is_group=False, created_by=uid)
    db.session.add(convo)
    db.session.flush()

    mutual = (
        Follow.query.filter(and_(Follow.follower_id == uid, Follow.following_id == oid)).count() > 0
        and Follow.query.filter(and_(Follow.follower_id == oid, Follow.following_id == uid)).count() > 0
    )

    is_private_gate = other_user.is_private and not other_user.is_professional
    # Restrict pushes messages into requests similar to Instagram's restricted inbox.
    restricted_request = _is_restricted_by(other_user_id, user_id)
    # For private accounts without mutual follows, create a request thread instead of blocking.
    receiver_is_request = bool(is_private_gate and not mutual or restricted_request)

    db.session.add(ConversationParticipant(conversation_id=convo.id, user_id=uid, role="admin", is_request=False))
    db.session.add(
        ConversationParticipant(
            conversation_id=convo.id,
            user_id=oid,
            role="member",
            is_request=receiver_is_request,
        )
    )
    db.session.commit()
    return convo


def create_group_conversation(creator_id: str, member_ids: Sequence[str], title: str | None = None) -> Conversation:
    creator_uuid = creator_id if isinstance(creator_id, uuid.UUID) else uuid.UUID(str(creator_id))
    members = {m if isinstance(m, uuid.UUID) else uuid.UUID(str(m)) for m in member_ids}
    members.add(creator_uuid)
    if len(members) > MAX_GROUP_MEMBERS:
        raise MessagingError("Group too large")
    convo = Conversation(is_group=True, created_by=creator_uuid, title=title or "New Group")
    db.session.add(convo)
    db.session.flush()
    for uid in members:
        db.session.add(
            ConversationParticipant(
                conversation_id=convo.id,
                user_id=uid,
                role="admin" if uid == creator_uuid else "member",
                is_request=False,
            )
        )
    db.session.commit()
    return convo


def assert_membership(conversation_id: str, user_id: str) -> ConversationParticipant:
    uid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
    cid = conversation_id if isinstance(conversation_id, uuid.UUID) else uuid.UUID(str(conversation_id))
    member = ConversationParticipant.query.filter_by(conversation_id=cid, user_id=uid).first()
    if not member:
        raise MessagingError("Not a participant")
    return member


def add_participants(conversation_id: str, actor_id: str, new_user_ids: Iterable[str]):
    actor = assert_membership(conversation_id, actor_id)
    if actor.role != "admin":
        raise MessagingError("Only admins can add members")
    existing_ids = {p.user_id for p in ConversationParticipant.query.filter_by(conversation_id=conversation_id).all()}
    for uid in new_user_ids:
        uid = uid if isinstance(uid, uuid.UUID) else uuid.UUID(str(uid))
        if uid in existing_ids:
            continue
        db.session.add(
            ConversationParticipant(
                conversation_id=conversation_id,
                user_id=uid,
                role="member",
                is_request=False,
            )
        )
    db.session.commit()


def remove_participant(conversation_id: str, actor_id: str, target_id: str):
    actor = assert_membership(conversation_id, actor_id)
    target = assert_membership(conversation_id, target_id)
    if actor.role != "admin":
        raise MessagingError("Only admins can remove members")
    if target.role == "admin" and target.user_id != actor_id:
        raise MessagingError("Cannot remove another admin")
    db.session.delete(target)
    db.session.commit()


def accept_request(conversation_id: str, user_id: str):
    member = assert_membership(conversation_id, user_id)
    member.is_request = False
    db.session.commit()


def set_theme(conversation_id: str, user_id: str, theme: str):
    member = assert_membership(conversation_id, user_id)
    member.theme = theme
    convo = Conversation.query.get(conversation_id)
    if convo:
        convo.theme = theme
    db.session.commit()


def save_message(
    conversation_id: str,
    sender_id: str,
    *,
    message_type: str,
    content: str | None = None,
    media_url: str | None = None,
    media_mime: str | None = None,
    media_size: int | None = None,
    duration_seconds: float | None = None,
    thumbnail_url: str | None = None,
    reply_to_id: str | None = None,
    is_vanish: bool = False,
    gif_provider: str | None = None,
    gif_id: str | None = None,
    autoplay: bool = True,
) -> Message:
    member = assert_membership(conversation_id, sender_id)
    if member.is_request:
        raise MessagingError("Conversation request not accepted")

    sender_uuid = sender_id if isinstance(sender_id, uuid.UUID) else uuid.UUID(str(sender_id))
    cid = conversation_id if isinstance(conversation_id, uuid.UUID) else uuid.UUID(str(conversation_id))
    others = ConversationParticipant.query.filter(
        ConversationParticipant.conversation_id == cid,
        ConversationParticipant.user_id != sender_uuid,
    ).all()
    for other in others:
        if _is_blocked(sender_uuid, str(other.user_id)):
            raise MessagingError("Blocked")

    if message_type == "gif":
        if not media_url:
            raise MessagingError("GIF url required")
        validate_gif_url(media_url)
        if gif_provider:
            validate_gif_provider(gif_provider)
    elif message_type == "voice":
        if not (media_url and media_mime and media_size is not None):
            raise MessagingError("Voice media required")
        validate_voice(media_url, media_mime, media_size)
    elif message_type == "file":
        if not (media_url and media_mime and media_size is not None):
            raise MessagingError("File media required")
        validate_file(media_url, media_mime, media_size)
    elif message_type == "video":
        if not (media_url and media_mime and media_size is not None):
            raise MessagingError("Video media required")
        validate_video(media_url, media_mime, media_size)
    elif message_type == "text":
        if not content:
            raise MessagingError("Content required")
        content = html.escape(content.strip())
    else:
        if not media_url:
            raise MessagingError("Media required")

    msg = Message(
        conversation_id=cid,
        sender_id=sender_uuid,
        message_type=message_type,
        content=content,
        media_url=media_url,
        media_mime_type=media_mime,
        media_size_bytes=media_size,
        duration_seconds=duration_seconds,
        thumbnail_url=thumbnail_url,
        reply_to_id=reply_to_id,
        is_vanish=is_vanish,
        gif_provider=gif_provider,
        gif_id=gif_id,
        autoplay=autoplay,
    )
    convo = Conversation.query.get(cid)
    if convo:
        convo.last_message_at = datetime.utcnow()
    db.session.add(msg)
    db.session.commit()
    return msg


def list_conversations(user_id: str):
    uid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
    return (
        Conversation.query.join(ConversationParticipant)
        .filter(ConversationParticipant.user_id == uid)
        .options(joinedload(Conversation.participants).joinedload(ConversationParticipant.user))
        .order_by(Conversation.last_message_at.desc().nullslast())
        .all()
    )


def get_conversation_detail(conversation_id: str, user_id: str) -> Conversation:
    """Return a conversation with participant user info after membership check."""
    assert_membership(conversation_id, user_id)
    convo = (
        Conversation.query.options(joinedload(Conversation.participants).joinedload(ConversationParticipant.user))
        .filter(Conversation.id == conversation_id)
        .first()
    )
    if not convo:
        raise MessagingError("Conversation not found")
    return convo


def fetch_messages(conversation_id: str, user_id: str, limit: int = 30, before: datetime | None = None):
    assert_membership(conversation_id, user_id)
    query = (
        Message.query.options(joinedload(Message.sender))
        .filter_by(conversation_id=conversation_id)
        .order_by(Message.created_at.desc())
    )
    if before:
        query = query.filter(Message.created_at < before)
    return list(reversed(query.limit(limit).all()))


def mark_read(conversation_id: str, user_id: str):
    member = assert_membership(conversation_id, user_id)
    member.last_read_at = datetime.utcnow()
    db.session.commit()


def toggle_reaction(message_id: str, user_id: str, reaction_type: str) -> MessageReaction | None:
    msg = Message.query.get(message_id)
    if not msg:
        raise MessagingError("Message not found")
    assert_membership(msg.conversation_id, user_id)
    existing = MessageReaction.query.filter_by(message_id=message_id, user_id=user_id).first()
    if existing and existing.reaction_type == reaction_type:
        db.session.delete(existing)
        db.session.commit()
        return None
    if existing:
        existing.reaction_type = reaction_type
        existing.created_at = datetime.utcnow()
    else:
        db.session.add(MessageReaction(message_id=message_id, user_id=user_id, reaction_type=reaction_type))
    db.session.commit()
    return MessageReaction.query.filter_by(message_id=message_id, user_id=user_id).first()


def report_message(message_id: str, reporter_id: str, reason: str) -> MessageReport:
    msg = Message.query.get(message_id)
    if not msg:
        raise MessagingError("Message not found")
    assert_membership(msg.conversation_id, reporter_id)
    report = MessageReport(message_id=message_id, reported_by=reporter_id, reason=reason[:255])
    db.session.add(report)
    db.session.commit()
    return report
