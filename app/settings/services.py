import uuid
from datetime import datetime
from flask import current_app
from app.extensions import db
from app.models import UserSetting, DataExportJob, DeviceSession, User


def _to_uuid(val):
    return val if isinstance(val, uuid.UUID) else uuid.UUID(str(val))


def get_or_create_settings(user_id):
    user_uuid = _to_uuid(user_id)
    settings = UserSetting.query.filter_by(user_id=user_uuid).first()
    if not settings:
        settings = UserSetting(user_id=user_uuid, theme=current_app.config.get("THEME_DEFAULT", "light"))
        db.session.add(settings)
        db.session.commit()
    return settings


def update_privacy(user_id, payload):
    settings = get_or_create_settings(user_id)
    user = User.query.get(_to_uuid(user_id))

    # Keep user.is_private in sync with the settings toggle so profile visibility actually changes
    new_is_private = bool(payload.get("is_private", user.is_private if user else settings.is_private))
    settings.is_private = new_is_private
    if user:
        user.is_private = new_is_private

    settings.show_activity = bool(payload.get("show_activity", settings.show_activity))
    settings.story_visibility = payload.get("story_visibility", settings.story_visibility)
    settings.dm_privacy = payload.get("dm_privacy", settings.dm_privacy)
    settings.search_visibility = bool(payload.get("search_visibility", settings.search_visibility))

    db.session.commit()
    return settings, user


def update_security(user_id, payload):
    settings = get_or_create_settings(user_id)
    settings.two_factor_enabled = bool(payload.get("two_factor_enabled", settings.two_factor_enabled))
    db.session.commit()
    return settings


def update_preferences(user_id, payload):
    settings = get_or_create_settings(user_id)
    if lang := payload.get("language"):
        settings.language = lang
    if theme := payload.get("theme"):
        settings.theme = theme
    settings.restricted_mode = bool(payload.get("restricted_mode", settings.restricted_mode))
    db.session.commit()
    return settings


def clear_caches(redis_client, user_id):
    redis_client.delete(f"session:{user_id}")
    redis_client.delete(f"profile:{user_id}")
    redis_client.delete(f"feed:{user_id}")


def create_export_job(user_id):
    job = DataExportJob(user_id=_to_uuid(user_id), token=str(uuid.uuid4()))
    db.session.add(job)
    db.session.commit()
    return job


def upsert_device_session(user_id, device, ip):
    user_uuid = _to_uuid(user_id)
    session = DeviceSession.query.filter_by(user_id=user_uuid, device=device).first()
    if not session:
        session = DeviceSession(user_id=user_uuid, device=device, ip_address=ip)
        db.session.add(session)
    else:
        session.ip_address = ip or session.ip_address
    session.last_active_at = datetime.utcnow()
    session.is_active = True
    db.session.commit()
    return session
