import re
import uuid
from typing import Iterable
from flask import current_app
from sqlalchemy.orm import selectinload
from app.extensions import db
from app.core.storage import get_s3_client, s3_public_prefix
from app.models import (
    User,
    Post,
    PostMedia,
    Hashtag,
    PostHashtag,
    PostTag,
    Location,
)
from app.notifications.notification_dispatcher import dispatch_notification
from app.notifications.notification_service import NotificationError
from .media_utils import upload_media, validate_media_files

# Use a word-boundary style negative lookbehind to avoid variable-width errors on Python 3.14
HASHTAG_PATTERN = re.compile(r"(?i)(?<!\w)#([a-z0-9_]{2,50})")
MENTION_PATTERN = re.compile(r"(?i)(?<!\w)@([a-z0-9_.]{2,50})")


def parse_hashtags(caption: str) -> set[str]:
    if not caption:
        return set()
    return set(match.group(1).lower() for match in HASHTAG_PATTERN.finditer(caption))


def parse_mentions(caption: str) -> set[str]:
    if not caption:
        return set()
    return set(match.group(1).lower() for match in MENTION_PATTERN.finditer(caption))


def ensure_location(name: str | None, lat: float | None, lng: float | None) -> Location | None:
    if not name:
        return None
    existing = Location.query.filter_by(name=name).first()
    if existing:
        return existing
    loc = Location(name=name, latitude=lat, longitude=lng)
    db.session.add(loc)
    db.session.flush()
    return loc


def sync_hashtags(post: Post, caption: str):
    tags = parse_hashtags(caption)
    if not tags:
        post.hashtags = []
        return
    hashtag_models: list[Hashtag] = []
    for tag in tags:
        hashtag = Hashtag.query.filter_by(name=tag).first()
        if not hashtag:
            hashtag = Hashtag(name=tag)
            db.session.add(hashtag)
            db.session.flush()
        hashtag_models.append(hashtag)
    post.hashtags = hashtag_models
    if len(tags) >= 3:
        _cache_trending(tags)


def sync_mentions(post: Post, caption: str):
    mentions = parse_mentions(caption)
    PostTag.query.filter_by(post_id=post.id).delete()
    if not mentions:
        return
    users = User.query.filter(User.username.in_(mentions)).all()
    for u in users:
        db.session.add(PostTag(post_id=post.id, tagged_user_id=u.id))
        if str(u.id) != str(post.user_id):
            try:
                dispatch_notification(
                    recipient_id=str(u.id),
                    actor_id=str(post.user_id),
                    ntype="mention_post",
                    reference_id=str(post.id),
                    metadata={"post_id": str(post.id)},
                    dedup_key=f"mention:{post.id}:{u.id}",
                )
            except NotificationError:
                pass


def _cache_trending(tags: Iterable[str]):
    r = current_app.redis_client
    for tag in tags:
        r.zincrby("trending:hashtags", 1, tag)
    r.expire("trending:hashtags", 3600)


def create_post(user_id: str, files: list, form_data: dict) -> Post:
    validate_media_files(files)
    user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
    # Form fields may come through as empty strings; coerce safely before math
    def _safe_float(value):
        return float(value) if value not in (None, "") else None
    loc = ensure_location(
        form_data.get("location_name"),
        form_data.get("location_latitude"),
        form_data.get("location_longitude"),
    )
    post = Post(
        user_id=user_uuid,
        caption=form_data.get("caption"),
        location=loc,
        hide_like_count=bool(form_data.get("hide_like_count")),
        branded_content_tag=form_data.get("branded_content_tag"),
    )
    db.session.add(post)
    db.session.flush()

    brightness = float(form_data.get("brightness") or 1.0)
    contrast = float(form_data.get("contrast") or 1.0)
    crop_box = None
    cx, cy, cw, ch = (
        _safe_float(form_data.get("crop_x")),
        _safe_float(form_data.get("crop_y")),
        _safe_float(form_data.get("crop_width")),
        _safe_float(form_data.get("crop_height")),
    )
    if all(val is not None for val in (cx, cy, cw, ch)) and cw and ch:
        crop_box = (cx, cy, cx + cw, cy + ch)
    image_filter = form_data.get("image_filter", "none")

    media_records: list[PostMedia] = []
    for idx, f in enumerate(files):
        meta = upload_media(str(user_uuid), f, brightness, contrast, crop_box, image_filter)
        media_records.append(
            PostMedia(
                post_id=post.id,
                media_type=meta["media_type"],
                media_url=meta["media_url"],
                thumbnail_url=meta.get("thumbnail_url"),
                order_index=idx,
                width=meta["width"],
                height=meta["height"],
                duration_seconds=meta["duration"],
            )
        )
    db.session.add_all(media_records)
    sync_hashtags(post, post.caption or "")
    sync_mentions(post, post.caption or "")
    db.session.commit()
    return post


def update_post_caption(
    user_id: str,
    post: Post,
    caption: str,
    branded_tag: str | None,
    hide_like_count: bool,
    location_name: str | None = None,
    location_latitude: float | None = None,
    location_longitude: float | None = None,
):
    if str(post.user_id) != str(user_id):
        raise PermissionError("Not authorized")
    post.caption = caption
    post.branded_content_tag = branded_tag
    post.hide_like_count = hide_like_count
    post.location = ensure_location(location_name, location_latitude, location_longitude)
    sync_hashtags(post, caption or "")
    sync_mentions(post, caption or "")
    db.session.commit()


def delete_post(user_id: str, post: Post):
    if str(post.user_id) != str(user_id):
        raise PermissionError("Not authorized")
    _delete_media_assets(post)
    db.session.delete(post)
    db.session.commit()


def toggle_archive(user_id: str, post: Post):
    if str(post.user_id) != str(user_id):
        raise PermissionError("Not authorized")
    post.is_archived = not post.is_archived
    db.session.commit()


def toggle_pin(user_id: str, post: Post):
    if str(post.user_id) != str(user_id):
        raise PermissionError("Not authorized")
    post.is_pinned = not post.is_pinned
    db.session.commit()


def get_post_with_media(post_id: str) -> Post | None:
    return (
        Post.query.options(selectinload(Post.media), selectinload(Post.hashtags), selectinload(Post.tags))
        .filter_by(id=post_id)
        .first()
    )


def _delete_media_assets(post: Post):
    bucket = None
    s3 = None
    try:
        bucket = current_app.config["AWS_S3_BUCKET"]
        s3 = get_s3_client()
    except Exception:
        return
    prefix = s3_public_prefix()
    for media in post.media:
        for url in filter(None, [media.media_url, media.thumbnail_url]):
            if url.startswith(prefix):
                key = url.replace(prefix, "", 1)
                try:
                    s3.delete_object(Bucket=bucket, Key=key)
                except Exception:
                    current_app.logger.warning("Failed to delete media %s", key)
