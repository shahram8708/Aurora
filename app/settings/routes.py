import uuid
import random
from datetime import timedelta
from flask import request, jsonify, render_template, current_app, flash, redirect, url_for, abort, session
from flask_jwt_extended import jwt_required, get_jwt_identity, unset_jwt_cookies
from app.extensions import db, csrf
from app.models import UserSetting, DataExportJob, DeviceSession, User, OAuthAccount
from app.email.email_service import send_email
from app.users.forms import PrivacyForm, ProfessionalForm
from . import settings_bp
from .services import (
    update_privacy,
    update_security,
    update_preferences,
    clear_caches,
    create_export_job,
    get_or_create_settings,
    upsert_device_session,
)
from .tasks import export_user_data


def _current_user_from_identity():
    user_id = get_jwt_identity()
    try:
        user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
    except (TypeError, ValueError):
        return None
    return User.query.filter_by(id=user_uuid, is_deleted=False).first()


@settings_bp.route("/api/privacy", methods=["POST"])
@csrf.exempt
@jwt_required()
def privacy_settings():
    user_id = get_jwt_identity()
    payload = request.get_json() or {}
    settings, user = update_privacy(user_id, payload)
    is_private = user.is_private if user else settings.is_private
    return jsonify({
        "is_private": is_private,
        "search_visibility": settings.search_visibility,
        "show_activity": settings.show_activity,
        "story_visibility": settings.story_visibility,
        "dm_privacy": settings.dm_privacy,
    })


@settings_bp.route("/api/security", methods=["POST"])
@csrf.exempt
@jwt_required()
def security_settings():
    user_id = get_jwt_identity()
    payload = request.get_json() or {}
    settings = update_security(user_id, payload)
    return jsonify({"two_factor_enabled": settings.two_factor_enabled})


@settings_bp.route("/api/preferences", methods=["POST"])
@csrf.exempt
@jwt_required()
def preference_settings():
    user_id = get_jwt_identity()
    payload = request.get_json() or {}
    settings = update_preferences(user_id, payload)
    return jsonify({"language": settings.language, "theme": settings.theme})


@settings_bp.route("/api/connected", methods=["POST"])
@csrf.exempt
@jwt_required()
def connect_account():
    user_id = get_jwt_identity()
    provider = (request.json.get("provider") if request.is_json else None) or ""
    provider = provider.lower().strip()
    metadata = request.json.get("metadata", {}) if request.is_json else {}
    otp_code = request.json.get("otp") if request.is_json else None
    if not provider:
        return jsonify({"error": "Provider is required"}), 400

    user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
    settings = get_or_create_settings(user_id)
    data = settings.linked_accounts or {}

    # Require email for Google linking and enforce OTP verification before attaching
    email = ""
    if isinstance(metadata, dict):
        email = (metadata.get("email") or "").strip().lower()
    if provider == "google":
        if not email:
            return jsonify({"error": "Email is required to link Google."}), 400
        if not otp_code:
            return jsonify({"error": "OTP is required"}), 400
        otp_key = f"otp:link:{provider}:{email}:{user_uuid}"
        stored = current_app.redis_client.get(otp_key)
        stored_val = stored.decode() if isinstance(stored, (bytes, bytearray)) else (stored if stored is not None else "")
        if not stored_val or stored_val != str(otp_code):
            return jsonify({"error": "Invalid or expired OTP"}), 400
        current_app.redis_client.delete(otp_key)

    data[provider] = metadata
    settings.linked_accounts = data

    # If an email is provided, persist a discoverable OAuthAccount so Google sign-in can map back to this user
    if email and provider in {"google", "apple", "facebook", "github", "twitter"}:
        existing_for_email = OAuthAccount.query.filter_by(provider=provider, provider_account_id=email).first()
        if existing_for_email and existing_for_email.user_id != user_uuid:
            return jsonify({"error": "That email is already linked to another account."}), 400
        oauth = OAuthAccount.query.filter_by(provider=provider, user_id=user_uuid).first()
        if not oauth:
            oauth = OAuthAccount(provider=provider, provider_account_id=email, user_id=user_uuid)
            db.session.add(oauth)
        elif not oauth.provider_account_id:
            oauth.provider_account_id = email

    db.session.commit()
    return jsonify({"linked_accounts": data})


@settings_bp.route("/api/connected/<provider>", methods=["DELETE"])
@csrf.exempt
@jwt_required()
def disconnect_account(provider):
    user_id = get_jwt_identity()
    user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
    provider_key = (provider or "").lower().strip()
    settings = get_or_create_settings(user_id)
    data = dict(settings.linked_accounts or {})
    # Drop both the provided casing and normalized casing for safety
    data.pop(provider, None)
    data.pop(provider_key, None)
    settings.linked_accounts = data
    OAuthAccount.query.filter_by(provider=provider_key, user_id=user_uuid).delete()
    db.session.commit()
    return jsonify({"linked_accounts": data})


@settings_bp.route("/api/connected/request-otp", methods=["POST"])
@csrf.exempt
@jwt_required()
def request_connect_otp():
    user_id = get_jwt_identity()
    payload = request.get_json() or {}
    provider = (payload.get("provider") or "").strip().lower()
    email = (payload.get("email") or "").strip().lower()
    if not provider or provider != "google":
        return jsonify({"error": "Only Google linking supports OTP flow."}), 400
    if not email:
        return jsonify({"error": "Email is required"}), 400
    code = f"{random.randint(0, 999999):06d}"
    key = f"otp:link:{provider}:{email}:{user_id}"
    current_app.redis_client.setex(key, timedelta(minutes=5), code)
    send_email(
        template_name="auth/login_otp",
        recipient=email,
        subject="Your link verification code",
        context={
            "user": {"name": email},
            "otp_code": code,
            "ip": request.remote_addr,
            "device": request.user_agent.string,
            "expires_minutes": 5,
        },
        priority="high",
    )
    return jsonify({"status": "sent"})


@settings_bp.route("/api/cache/clear", methods=["POST"])
@csrf.exempt
@jwt_required()
def clear_cache():
    user_id = get_jwt_identity()
    clear_caches(current_app.redis_client, user_id)
    return jsonify({"status": "cleared"})


@settings_bp.route("/api/export", methods=["POST"])
@csrf.exempt
@jwt_required()
def export_data():
    user_id = get_jwt_identity()
    job = create_export_job(user_id)
    export_user_data.delay(str(job.id))
    return jsonify({"job_id": str(job.id), "status": "queued"})


@settings_bp.route("/api/export/<uuid:job_id>", methods=["GET"])
@jwt_required()
def export_status(job_id):
    job = DataExportJob.query.get_or_404(job_id)
    return jsonify({"status": job.status, "url": job.storage_url, "expires_at": job.expires_at.isoformat() if job.expires_at else None})


@settings_bp.route("/api/sessions", methods=["GET"])
@jwt_required()
def list_devices():
    user_id = get_jwt_identity()
    user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
    sessions = DeviceSession.query.filter_by(user_id=user_uuid).order_by(DeviceSession.last_active_at.desc()).limit(20).all()
    return jsonify([
        {
            "device": s.device,
            "ip": s.ip_address,
            "last_active_at": s.last_active_at.isoformat(),
            "active": s.is_active,
        }
        for s in sessions
    ])


@settings_bp.route("/api/sessions", methods=["DELETE"])
@csrf.exempt
@jwt_required()
def revoke_all_sessions():
    user_id = get_jwt_identity()
    user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
    DeviceSession.query.filter_by(user_id=user_uuid).update({"is_active": False}, synchronize_session=False)
    db.session.commit()
    return jsonify({"status": "revoked"})


@settings_bp.route("/deactivate", methods=["POST"])
@jwt_required()
def deactivate_account():
    user = _current_user_from_identity()
    if not user:
        abort(404)
    user.is_active = False
    db.session.commit()
    flash("Account deactivated. Log in anytime to reactivate.", "warning")
    resp = redirect(url_for("auth.login"))
    unset_jwt_cookies(resp)
    session.clear()
    return resp


@settings_bp.route("/delete", methods=["POST"])
@jwt_required()
def delete_account():
    user = _current_user_from_identity()
    if not user:
        abort(404)
    db.session.delete(user)
    db.session.commit()
    flash("Account deleted permanently", "warning")
    resp = redirect(url_for("auth.login"))
    unset_jwt_cookies(resp)
    session.clear()
    return resp


@settings_bp.route("/view", methods=["GET"])
@jwt_required()
def settings_page():
    user_id = get_jwt_identity()
    user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
    user = User.query.get(user_uuid)
    settings = get_or_create_settings(user_uuid)

    # Record the current session so Device Sessions has real data
    device_label = (request.user_agent.string or "Unknown device")[:120]
    client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr
    if user:
        upsert_device_session(user_uuid, device_label, client_ip)

    privacy_form = PrivacyForm(obj=user) if user else None
    professional_form = ProfessionalForm(obj=user) if user else None
    return render_template(
        "settings/settings.html",
        settings=settings,
        user=user,
        privacy_form=privacy_form,
        professional_form=professional_form,
    )


