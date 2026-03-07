import json
import os
import uuid
from datetime import datetime, timedelta
from flask import current_app
from sqlalchemy import desc
from sqlalchemy.orm import selectinload
from app.extensions import db, celery
from sqlalchemy.exc import IntegrityError
from app.models import Reel, ReelMusic, ReelEffect, ReelSticker, ReelInsight, User, ARFilter, ReelLike, ReelComment, ReelSave
from .video_utils import (
    VideoValidationError,
    validate_video_file,
    store_temp,
    hash_file,
    prevent_duplicate,
    probe_video,
    compress_video,
    generate_thumbnail,
    upload_assets,
    merge_voiceover,
    probe_audio,
    validate_voiceover_duration,
)
from .analytics import ensure_insight, increment_view, add_watch_time, increment_comment


def _parse_json(value):
    if not value:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def create_reel(user: User, file_storage, form_data: dict, voiceover_file=None, background_image=None) -> Reel:
    filename = validate_video_file(file_storage)
    tmp_video = store_temp(file_storage)
    voice_tmp = None
    duplicate_key = None
    try:
        duplicate_key = prevent_duplicate(hash_file(tmp_video), str(user.id))
        meta = probe_video(tmp_video)
        speed_factor = float(form_data.get("speed_factor") or 1.0)
        processed_video = compress_video(tmp_video, speed_factor)
        voiceover_url = None
        mix_ratio = None
        voice_duration = None
        music_obj = None
        music_id = form_data.get("music_id")
        if music_id:
            music_obj = ReelMusic.query.get(music_id)
            if not music_obj:
                raise VideoValidationError("Invalid music")
            music_obj.usage_count = (music_obj.usage_count or 0) + 1
        if voiceover_file:
            voice_tmp = store_temp(voiceover_file)
            voice_duration = probe_audio(voice_tmp)
            validate_voiceover_duration(meta["duration"], voice_duration)
            mix_ratio = float(form_data.get("mix_ratio") or 0.5)
            processed_video = merge_voiceover(processed_video, voice_tmp, mix_ratio)
        filter_id = form_data.get("filter_id")
        if filter_id and not ARFilter.query.get(filter_id):
            raise VideoValidationError("Invalid AR filter")
        remix_source = form_data.get("original_reel_id") or None
        if remix_source:
            try:
                remix_source = uuid.UUID(str(remix_source))
            except (ValueError, AttributeError) as exc:
                raise VideoValidationError("Invalid remix source") from exc
        thumb_path = generate_thumbnail(processed_video)
        bg_tmp = None
        bg_url = None
        if background_image:
            bg_tmp = store_temp(background_image)
        uploads = upload_assets(str(user.id), processed_video, thumb_path, voice_tmp if voiceover_file else None, bg_tmp)
        scheduled_at = form_data.get("scheduled_at")
        scheduled_dt = None
        if scheduled_at:
            if isinstance(scheduled_at, str):
                scheduled_dt = datetime.fromisoformat(scheduled_at)
            elif isinstance(scheduled_at, datetime):
                scheduled_dt = scheduled_at
        if scheduled_dt:
            if scheduled_dt < datetime.utcnow():
                raise VideoValidationError("Cannot schedule in the past")
            if scheduled_dt > datetime.utcnow() + timedelta(days=current_app.config["REEL_MAX_SCHEDULE_DAYS"]):
                raise VideoValidationError("Schedule window too far")
        monetization_enabled = bool(form_data.get("monetization_enabled")) and user.is_professional
        text_overlays = _parse_json(form_data.get("text_overlays"))
        if text_overlays and len(text_overlays) > current_app.config["REEL_MAX_TEXT_OVERLAYS"]:
            raise VideoValidationError("Too many text overlays")
        effects_metadata = _parse_json(form_data.get("effects_metadata"))
        stickers_metadata = _parse_json(form_data.get("stickers_metadata"))
        reel = Reel(
            user_id=user.id,
            caption=form_data.get("caption"),
            video_url=uploads["video_url"],
            thumbnail_url=uploads["thumbnail_url"],
            music_id=music_obj.id if music_obj else None,
            speed_factor=speed_factor,
            is_remix=bool(form_data.get("is_remix")),
            original_reel_id=remix_source,
            allow_download=bool(form_data.get("allow_download", True)),
            monetization_enabled=monetization_enabled,
            scheduled_at=scheduled_dt,
            is_published=False if scheduled_dt else True,
            duration_seconds=meta["duration"],
            width=meta["width"],
            height=meta["height"],
            text_overlays=text_overlays,
            effects_metadata=effects_metadata,
            stickers_metadata=stickers_metadata,
            voiceover_url=uploads.get("voiceover_url"),
            voiceover_duration=voice_duration,
            mix_ratio=mix_ratio,
            green_screen_background_url=uploads.get("background_url"),
            green_screen_subject_mask=bool(form_data.get("green_screen_subject_mask")),
            countdown_seconds=int(form_data.get("countdown_seconds") or 0),
            countdown_autostart=bool(form_data.get("countdown_autostart")),
            filter_id=filter_id,
        )
        db.session.add(reel)
        db.session.flush()
        ensure_insight(reel.id)
        _persist_effects_and_stickers(reel, effects_metadata, stickers_metadata)
        _update_music_usage(reel.music_id)
        db.session.commit()
        if scheduled_dt:
            schedule_publish(reel.id, scheduled_dt)
        return reel
    except Exception:
        if duplicate_key:
            current_app.redis_client.delete(duplicate_key)
        raise
    finally:
        for path in [locals().get("tmp_video"), locals().get("processed_video"), locals().get("thumb_path"), locals().get("bg_tmp"), locals().get("voice_tmp")]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass


def _persist_effects_and_stickers(reel: Reel, effects_metadata, stickers_metadata):
    if effects_metadata:
        for e in effects_metadata:
            db.session.add(ReelEffect(reel_id=reel.id, name=e.get("name", "custom"), metadata_json=e))
    if stickers_metadata:
        for s in stickers_metadata:
            db.session.add(ReelSticker(reel_id=reel.id, type=s.get("type", "custom"), metadata_json=s))


def _update_music_usage(music_id):
    if not music_id:
        return
    db.session.query(ReelMusic).filter(ReelMusic.id == music_id).update({ReelMusic.usage_count: ReelMusic.usage_count + 1})
    db.session.commit()


def schedule_publish(reel_id, scheduled_at: datetime):
    celery.send_task("app.reels.tasks.publish_reel", args=[str(reel_id)], eta=scheduled_at)


def publish_reel_now(reel_id):
    db.session.query(Reel).filter(Reel.id == reel_id).update({Reel.is_published: True})
    db.session.commit()


def list_published_reels(limit=20, offset=0):
    return (
        Reel.query.filter(Reel.is_published.is_(True))
        .order_by(desc(Reel.created_at))
        .options(selectinload(Reel.music), selectinload(Reel.effects), selectinload(Reel.stickers), selectinload(Reel.insights))
        .limit(limit)
        .offset(offset)
        .all()
    )


def _ensure_uuid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Invalid reel id") from exc


def toggle_reel_save(user_id, reel_id) -> bool:
    """Toggle save for a reel; returns True if saved after operation."""
    uid = _ensure_uuid(user_id)
    rid = _ensure_uuid(reel_id)
    existing = ReelSave.query.filter_by(user_id=uid, reel_id=rid).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return False
    db.session.add(ReelSave(user_id=uid, reel_id=rid))
    db.session.commit()
    return True


def get_reel_comments(reel_id, limit=50):
    reel_uuid = _ensure_uuid(reel_id)
    capped_limit = max(1, min(int(limit or 50), 200))
    comments = (
        ReelComment.query.join(User, User.id == ReelComment.user_id)
        .filter(ReelComment.reel_id == reel_uuid)
        .order_by(ReelComment.created_at.desc())
        .limit(capped_limit)
        .all()
    )
    payload = []
    for comment in reversed(comments):  # oldest to newest for UI consistency
        user = comment.user
        payload.append(
            {
                "id": str(comment.id),
                "user": user.username if user else None,
                "user_id": str(comment.user_id),
                "content": comment.content,
                "avatar": getattr(user, "avatar_url", None)
                or getattr(user, "profile_photo_url", None)
                or getattr(user, "profile_photo", None)
                or None,
                "created_at": (comment.created_at or datetime.utcnow()).isoformat() + "Z",
            }
        )
    return payload


def add_reel_comment(reel_id, user: User, content: str):
    reel_uuid = _ensure_uuid(reel_id)
    comment = ReelComment(reel_id=reel_uuid, user_id=user.id, content=content)
    db.session.add(comment)
    db.session.flush()
    payload = {
        "id": str(comment.id),
        "user": user.username,
        "user_id": str(user.id),
        "content": comment.content,
        "avatar": getattr(user, "avatar_url", None)
        or getattr(user, "profile_photo_url", None)
        or getattr(user, "profile_photo", None)
        or None,
        "created_at": (comment.created_at or datetime.utcnow()).isoformat() + "Z",
    }
    db.session.commit()
    increment_comment(reel_id)
    return payload


def add_reel_like(reel_id, user: User) -> bool:
    reel_uuid = _ensure_uuid(reel_id)
    existing = ReelLike.query.filter_by(reel_id=reel_uuid, user_id=user.id).first()
    if existing:
        return False
    like = ReelLike(reel_id=reel_uuid, user_id=user.id)
    db.session.add(like)
    try:
        db.session.commit()
        return True
    except IntegrityError:
        db.session.rollback()
        return False


def get_reel_likes(reel_id):
    reel_uuid = _ensure_uuid(reel_id)
    likes = (
        ReelLike.query.join(User, User.id == ReelLike.user_id)
        .filter(ReelLike.reel_id == reel_uuid)
        .order_by(ReelLike.created_at.desc())
        .all()
    )
    payload = []
    for like in likes:
        user = like.user
        if not user:
            continue
        payload.append(
            {
                "user_id": str(user.id),
                "username": user.username,
                "avatar": getattr(user, "avatar_url", None)
                or getattr(user, "profile_photo_url", None)
                or getattr(user, "profile_photo", None)
                or None,
            }
        )
    return payload


def track_view_once(reel_id, viewer_id: str):
    if not viewer_id:
        return
    key = f"reel:view:{reel_id}:{viewer_id}"
    if current_app.redis_client.setnx(key, 1):
        current_app.redis_client.expire(key, 6 * 3600)
        increment_view(reel_id)
    # Persist a seen marker so feed can prioritize new reels first
    try:
        seen_key = f"user:{viewer_id}:seen_reels"
        current_app.redis_client.sadd(seen_key, str(reel_id))
        ttl = current_app.config.get("REEL_SEEN_TTL", 30 * 24 * 3600)
        current_app.redis_client.expire(seen_key, ttl)
    except Exception:
        pass


def record_watch(reel_id, viewer_id: str, seconds: float):
    if seconds <= 0:
        return
    add_watch_time(reel_id, seconds)


def get_reel(reel_id):
    return Reel.query.options(selectinload(Reel.music), selectinload(Reel.effects), selectinload(Reel.stickers)).get(reel_id)
