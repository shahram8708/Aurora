import io
import json
import uuid
from datetime import datetime, timedelta
from PIL import Image
from flask import current_app
from sqlalchemy import or_, exists
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from app.extensions import db, celery
from app.core.storage import get_s3_client, s3_public_url
from app.models import (
    Story,
    StorySticker,
    StoryInsight,
    StoryArchive,
    StoryHighlight,
    StoryHighlightItem,
    StoryView,
    StoryLike,
    StoryReply,
    ReelMusic,
    Follow,
    CloseFriend,
    Block,
    Mute,
)
from app.models import UserSetting
from app.reels.video_utils import probe_video, VideoValidationError, store_temp, validate_voiceover_duration

ALLOWED_IMAGE_MIME = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_VIDEO_MIME = {"video/mp4"}


def _ensure_insight(story_uuid):
    """Make sure a StoryInsight row exists; tolerate concurrent inserts."""
    insight = StoryInsight.query.filter_by(story_id=story_uuid).first()
    if insight:
        return insight
    db.session.add(StoryInsight(story_id=story_uuid))
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        insight = StoryInsight.query.filter_by(story_id=story_uuid).first()
    return insight


def _to_uuid(val):
    return val if isinstance(val, uuid.UUID) else uuid.UUID(str(val))


def can_view_story(owner_id: str, viewer_id: str | None, story: Story | None = None) -> bool:
    """Evaluate story visibility against the owner's settings and per-story close-friends flag."""
    owner_uuid = _to_uuid(owner_id)
    try:
        viewer_uuid = _to_uuid(viewer_id) if viewer_id else None
    except (TypeError, ValueError):
        viewer_uuid = None

    # Blocks hide stories entirely
    if viewer_uuid and Block.query.filter(
        (Block.user_id == owner_uuid) & (Block.target_id == viewer_uuid)
        | (Block.user_id == viewer_uuid) & (Block.target_id == owner_uuid)
    ).first():
        return False

    # Owners can always view their own stories.
    if viewer_uuid and viewer_uuid == owner_uuid:
        return True

    # Close friends story overrides global visibility: only allow listed close friends.
    if story and story.is_close_friends:
        if not viewer_uuid:
            return False
        return bool(CloseFriend.query.filter_by(user_id=owner_uuid, target_id=viewer_uuid).first())

    settings = UserSetting.query.filter_by(user_id=owner_uuid).first()
    visibility = (settings.story_visibility if settings else "followers").lower()

    if visibility == "everyone":
        return True
    if visibility == "followers":
        if not viewer_uuid:
            return False
        return bool(Follow.query.filter_by(follower_id=viewer_uuid, following_id=owner_uuid).first())
    if visibility == "close_friends":
        if not viewer_uuid:
            return False
        return bool(CloseFriend.query.filter_by(user_id=owner_uuid, target_id=viewer_uuid).first())
    return False


def _rate_limit_story(user_id: str):
    key = f"story:limit:{user_id}"
    count = current_app.redis_client.incr(key)
    current_app.redis_client.expire(key, 3600)
    if count > current_app.config["STORY_UPLOAD_LIMIT_PER_HOUR"]:
        raise VideoValidationError("Story upload limit reached")


def _upload_to_s3(user_id: str, content: bytes, suffix: str, content_type: str) -> str:
    s3 = get_s3_client()
    bucket = current_app.config["AWS_S3_BUCKET"]
    key = f"users/{user_id}/stories/{uuid.uuid4().hex}_{suffix}"
    s3.put_object(Body=content, Bucket=bucket, Key=key, ACL="public-read", ContentType=content_type)
    return s3_public_url(key)


def _process_image(file_storage) -> tuple[str, str]:
    if file_storage.mimetype not in ALLOWED_IMAGE_MIME:
        raise VideoValidationError("Invalid image type")
    img = Image.open(file_storage.stream).convert("RGB")
    img.thumbnail((1080, 1920))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", optimize=True, quality=88)
    buf.seek(0)
    thumb = img.copy()
    thumb.thumbnail((320, 320))
    tbuf = io.BytesIO()
    thumb.save(tbuf, format="JPEG", optimize=True, quality=80)
    tbuf.seek(0)
    return buf.getvalue(), tbuf.getvalue()


def _process_video(file_storage) -> tuple[str, float]:
    if file_storage.mimetype not in ALLOWED_VIDEO_MIME:
        raise VideoValidationError("Invalid video type")
    if file_storage.content_length and file_storage.content_length > current_app.config["STORY_MAX_SIZE_MB"] * 1024 * 1024:
        raise VideoValidationError("Video too large")
    tmp = store_temp(file_storage)
    meta = probe_video(tmp)
    if meta["duration"] > current_app.config["STORY_MAX_DURATION_SEC"]:
        raise VideoValidationError("Story video too long")
    return tmp, meta["duration"]


def create_story(user_id: str, form_data: dict, file_storage=None) -> Story:
    user_uuid = _to_uuid(user_id)
    _rate_limit_story(user_id)
    story_type = form_data.get("story_type") or "text"
    is_close = bool(form_data.get("is_close_friends"))
    stickers = form_data.get("stickers")
    drawing_json = form_data.get("drawing_json")
    music_id = form_data.get("music_id")
    link_url = form_data.get("link_url")

    media_url = None
    thumb_url = None
    duration = None
    if music_id:
        if not ReelMusic.query.get(music_id):
            raise VideoValidationError("Invalid music selection")
    if story_type == "photo" and file_storage:
        img_bytes, thumb_bytes = _process_image(file_storage)
        media_url = _upload_to_s3(user_id, img_bytes, "photo.jpg", "image/jpeg")
        thumb_url = _upload_to_s3(user_id, thumb_bytes, "thumb.jpg", "image/jpeg")
    elif story_type == "video" and file_storage:
        tmp, duration = _process_video(file_storage)
        with open(tmp, "rb") as fh:
            media_bytes = fh.read()
        media_url = _upload_to_s3(user_id, media_bytes, "video.mp4", "video/mp4")
    elif story_type == "text":
        media_url = None
    else:
        raise VideoValidationError("Invalid story payload")

    expires_at = datetime.utcnow() + timedelta(hours=24)
    story = Story(
        user_id=user_uuid,
        media_url=media_url,
        thumbnail_url=thumb_url,
        text_content=form_data.get("text_content"),
        story_type=story_type,
        is_close_friends=is_close,
        expires_at=expires_at,
        drawing_json=json.loads(drawing_json) if drawing_json else None,
        background_music_id=music_id,
    )
    db.session.add(story)
    db.session.flush()
    db.session.add(StoryInsight(story_id=story.id))
    if link_url:
        stickers = stickers or []
        if isinstance(stickers, str):
            try:
                stickers = json.loads(stickers)
            except json.JSONDecodeError:
                stickers = []
        if not isinstance(stickers, list):
            stickers = []
        stickers.append({"type": "link", "url": link_url})
    _persist_stickers(story.id, stickers)
    db.session.commit()
    schedule_expiry(str(story.id), expires_at)
    return story


def _persist_stickers(story_id, stickers_raw):
    payload = None
    if stickers_raw:
        payload = stickers_raw if isinstance(stickers_raw, (list, dict)) else json.loads(stickers_raw)
    if not payload:
        return
    if isinstance(payload, dict):
        payload = [payload]
    for s in payload:
        db.session.add(StorySticker(story_id=story_id, type=s.get("type", "custom"), metadata_json=s))


def register_view(story_id, viewer_id: str):
    viewer_uuid = _to_uuid(viewer_id)
    story_uuid = _to_uuid(story_id)
    inserted = False
    try:
        db.session.add(StoryView(story_id=story_uuid, viewer_id=viewer_uuid))
        # Ensure insight row exists without breaking on duplicates
        insight = StoryInsight.query.filter_by(story_id=story_uuid).first()
        if not insight:
            db.session.add(StoryInsight(story_id=story_uuid, view_count=0, replies_count=0))
        db.session.flush()
        inserted = True
    except IntegrityError:
        db.session.rollback()
    if inserted:
        db.session.query(StoryInsight).filter_by(story_id=story_uuid).update({StoryInsight.view_count: StoryInsight.view_count + 1})
        db.session.commit()


def register_reply(story_id):
    story_uuid = _to_uuid(story_id)
    _ensure_insight(story_uuid)
    db.session.query(StoryInsight).filter_by(story_id=story_uuid).update({StoryInsight.replies_count: StoryInsight.replies_count + 1})
    db.session.commit()


def create_story_reply(story_id: str, user_id: str, content: str) -> StoryReply:
    story_uuid = _to_uuid(story_id)
    user_uuid = _to_uuid(user_id)
    sanitized = (content or "").strip()
    if not sanitized:
        raise ValueError("Reply required")
    if len(sanitized) > 500:
        raise ValueError("Reply too long")
    _ensure_insight(story_uuid)
    reply = StoryReply(story_id=story_uuid, user_id=user_uuid, content=sanitized)
    db.session.add(reply)
    db.session.commit()
    register_reply(story_id)
    return reply


def toggle_story_like(story_id: str, user_id: str) -> tuple[int, bool]:
    story_uuid = _to_uuid(story_id)
    user_uuid = _to_uuid(user_id)
    existing = StoryLike.query.filter_by(story_id=story_uuid, user_id=user_uuid).first()
    if existing:
        db.session.delete(existing)
        liked = False
    else:
        db.session.add(StoryLike(story_id=story_uuid, user_id=user_uuid))
        liked = True
    db.session.commit()
    count = StoryLike.query.filter_by(story_id=story_uuid).count()
    return count, liked


def schedule_expiry(story_id: str, expires_at: datetime):
    celery.send_task("app.stories.tasks.expire_story", args=[story_id], eta=expires_at)


def expire_story(story_id: str):
    story = Story.query.get(story_id)
    if not story:
        return
    archive = StoryArchive(
        id=story.id,
        user_id=story.user_id,
        media_url=story.media_url,
        text_content=story.text_content,
        story_type=story.story_type,
        created_at_original=story.created_at,
        expired_at=story.expires_at,
    )
    db.session.add(archive)
    db.session.delete(story)
    db.session.commit()


def create_highlight(user_id: str, title: str, cover_image_url: str | None):
    user_uuid = _to_uuid(user_id)
    highlight = StoryHighlight(user_id=user_uuid, title=title, cover_image=cover_image_url)
    db.session.add(highlight)
    db.session.commit()
    return highlight


def add_to_highlight(highlight_id: int, story_id: str):
    story_uuid = _to_uuid(story_id)
    item = StoryHighlightItem(highlight_id=highlight_id, story_id=story_uuid)
    db.session.add(item)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    return item


def remove_from_highlight(item_id: int):
    StoryHighlightItem.query.filter_by(id=item_id).delete()
    db.session.commit()


def get_active_stories_for_user(user_id: str):
    user_uuid = _to_uuid(user_id)
    now = datetime.utcnow()
    return (
        Story.query.options(selectinload(Story.stickers))
        .filter(Story.user_id == user_uuid, Story.expires_at > now)
        .order_by(Story.created_at.desc())
        .all()
    )


def get_story_feed_for_viewer(viewer_id: str):
    viewer_uuid = _to_uuid(viewer_id)
    now = datetime.utcnow()
    following = db.session.query(Follow.following_id).filter(Follow.follower_id == viewer_uuid)
    muted = db.session.query(Mute.target_id).filter(Mute.user_id == viewer_uuid)
    blocked = db.session.query(Block.target_id).filter(Block.user_id == viewer_uuid)
    blocked_by = db.session.query(Block.user_id).filter(Block.target_id == viewer_uuid)
    close_friend_allowed = or_(
        Story.is_close_friends.is_(False),
        exists().where(
            CloseFriend.user_id == Story.user_id,
            CloseFriend.target_id == viewer_uuid,
        ),
    )
    stories = (
        Story.query.options(selectinload(Story.stickers), selectinload(Story.user))
        .outerjoin(UserSetting, UserSetting.user_id == Story.user_id)
        .filter(Story.expires_at > now)
        .filter(~Story.user_id.in_(blocked))
        .filter(~Story.user_id.in_(blocked_by))
        .filter(~Story.user_id.in_(muted))
        .filter(
            or_(
                Story.user_id == viewer_uuid,  # my stories
                Story.user_id.in_(following),  # people I follow
                UserSetting.story_visibility.is_(True),  # legacy bool safeguard (none here but keep safety)
                UserSetting.story_visibility == "everyone",  # explicitly open to everyone
            )
        )
        .filter(close_friend_allowed)
        .order_by(Story.created_at.desc())
        .all()
    )
    return [story for story in stories if can_view_story(story.user_id, viewer_id, story)]
