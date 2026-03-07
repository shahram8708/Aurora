import random
import secrets
import logging
import uuid
from datetime import datetime, timedelta
from flask import render_template, redirect, url_for, flash, request, current_app, session, jsonify, make_response
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    set_access_cookies,
    set_refresh_cookies,
    unset_jwt_cookies,
    jwt_required,
    get_jwt_identity,
)
from sqlalchemy import or_
from app.extensions import db, bcrypt, limiter, oauth, csrf
from app.models import User, PasswordResetToken, EmailVerificationToken, OAuthAccount
from app.email.email_service import send_email
from app.core.tokens import generate_token, load_token
from app.auth.forms import SignupForm, LoginForm, RequestResetForm, ResetPasswordForm, VerifyOTPForm
from app.core.security import is_strong_password
from . import auth_bp
from app.notifications.notification_dispatcher import dispatch_notification
from app.notifications.notification_service import NotificationError
from app.settings.services import upsert_device_session

security_log = logging.getLogger("security")


@auth_bp.route("/signup", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def signup():
    form = SignupForm()
    if form.validate_on_submit():
        if not is_strong_password(form.password.data):
            flash("Password does not meet complexity requirements", "danger")
            return render_template("auth/signup.html", form=form)
        user = User(
            email=form.email.data.lower(),
            phone=form.phone.data,
            username=form.username.data.lower(),
            name=form.name.data,
            password_hash=bcrypt.generate_password_hash(form.password.data).decode("utf-8"),
            terms_accepted_at=datetime.utcnow(),
        )
        db.session.add(user)
        db.session.commit()

        token_value = generate_token({"user_id": str(user.id)}, expires_in=86400)
        token = EmailVerificationToken(
            user_id=user.id,
            token=token_value,
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )
        db.session.add(token)
        db.session.commit()

        verify_link = url_for("auth.verify_email", token=token_value, _external=True)
        send_email(
            template_name="auth/email_verification",
            recipient=user.email,
            subject="Verify your email",
            context={
                "user": {"name": user.name or user.username},
                "verify_link": verify_link,
                "expires_hours": 24,
                "security_message": "For your protection, this link expires in 24 hours and works only once.",
            },
            priority="high",
        )
        flash("Account created. Check your email to verify.", "success")
        return redirect(url_for("auth.verify_email"))
    return render_template("auth/signup.html", form=form)


@auth_bp.route("/verify-email")
def verify_email():
    token_value = request.args.get("token")
    if not token_value:
        return render_template("auth/verify_email.html")
    data = load_token(token_value, max_age=86400)
    if not data:
        flash("Token expired or invalid", "danger")
        return redirect(url_for("auth.login"))
    token = EmailVerificationToken.query.filter_by(token=token_value, used=False).first()
    if not token or token.expires_at < datetime.utcnow():
        flash("Token expired or used", "danger")
        return redirect(url_for("auth.login"))
    user = User.query.get(token.user_id)
    if not user:
        flash("User not found", "danger")
        return redirect(url_for("auth.login"))
    user.email_verified = True
    token.used = True
    db.session.commit()
    flash("Email verified. You can login now.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter(
            or_(User.email == form.login.data.lower(), User.username == form.login.data.lower())
        ).first()
        if not user:
            security_log.warning("Login failed: unknown user", extra={"login": form.login.data})
            flash("Invalid credentials", "danger")
            return render_template("auth/login.html", form=form)
        if user.is_locked():
            flash("Account locked. Try again later.", "danger")
            return render_template("auth/login.html", form=form)
        if not bcrypt.check_password_hash(user.password_hash, form.password.data):
            user.register_failure()
            db.session.commit()
            security_log.warning("Login failed: bad password", extra={"user_id": str(user.id)})
            flash("Invalid credentials", "danger")
            return render_template("auth/login.html", form=form)
        if not user.email_verified:
            flash("Please verify your email first", "warning")
            return redirect(url_for("auth.login"))
        if user.is_deleted:
            flash("Account deleted. Please sign up again.", "danger")
            return render_template("auth/login.html", form=form)
        if not user.is_active:
            flash("Account was deactivated. Log in to reactivate.", "warning")

        user.reset_failures()
        db.session.commit()

        security_log.info("Password accepted", extra={"user_id": str(user.id)})

        otp_code = f"{random.randint(0, 999999):06d}"
        current_app.redis_client.setex(f"otp:login:{user.id}", timedelta(minutes=5), otp_code)
        session["pending_user_id"] = str(user.id)
        send_email(
            template_name="auth/login_otp",
            recipient=user.email,
            subject="Your login code",
            context={
                "user": {"name": user.name or user.username},
                "otp_code": otp_code,
                "ip": request.remote_addr,
                "device": request.user_agent.string,
                "expires_minutes": 5,
            },
            priority="high",
        )
        try:
            dispatch_notification(
                recipient_id=str(user.id),
                actor_id=None,
                ntype="login_new_device",
                reference_id=str(user.id),
                metadata={"ip": request.remote_addr, "device": request.user_agent.string},
                send_email=False,
            )
        except NotificationError:
            pass
        flash("Enter the code sent to your email", "info")
        return redirect(url_for("auth.verify_otp"))
    return render_template("auth/login.html", form=form)


@auth_bp.route("/verify-otp", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def verify_otp():
    form = VerifyOTPForm()
    user_id = session.get("pending_user_id")
    if not user_id:
        flash("No pending login", "danger")
        return redirect(url_for("auth.login"))
    try:
        user_uuid = uuid.UUID(str(user_id))
    except ValueError:
        session.pop("pending_user_id", None)
        flash("Invalid session. Please login again.", "danger")
        return redirect(url_for("auth.login"))

    user = User.query.get(user_uuid)
    if not user:
        flash("User not found", "danger")
        session.pop("pending_user_id", None)
        return redirect(url_for("auth.login"))
    if form.validate_on_submit():
        key = f"otp:login:{user.id}"
        code = current_app.redis_client.get(key)
        if not code or code != form.otp.data:
            flash("Invalid or expired code", "danger")
            return render_template("auth/verify_otp.html", form=form)
        current_app.redis_client.delete(key)
        session.pop("pending_user_id", None)
        if user.is_deleted:
            flash("Account deleted. Please sign up again.", "danger")
            return redirect(url_for("auth.login"))
        if not user.is_active:
            user.is_active = True
            user.is_deleted = False
            db.session.commit()
        security_log.info("OTP verified", extra={"user_id": str(user.id)})
        device_label = (request.user_agent.string or "Unknown device")[:120]
        client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr
        upsert_device_session(user.id, device_label, client_ip)
        access_token = create_access_token(identity=str(user.id), additional_claims={"username": user.username})
        refresh_token = create_refresh_token(identity=str(user.id))
        resp = make_response(redirect(url_for("users.dashboard")))
        set_access_cookies(resp, access_token)
        set_refresh_cookies(resp, refresh_token)
        flash("Logged in", "success")
        return resp
    return render_template("auth/verify_otp.html", form=form)


@auth_bp.route("/refresh", methods=["POST"])
@csrf.exempt  # Refresh uses JWT double-submit; skip form CSRF validation
@jwt_required(refresh=True)
def refresh_token():
    identity = get_jwt_identity()
    access_token = create_access_token(identity=identity)
    resp = jsonify(access_token=access_token)
    set_access_cookies(resp, access_token)
    return resp


@auth_bp.route("/logout", methods=["POST"])
@jwt_required(optional=True)
def logout():
    """Log out the user and clear JWT cookies, returning JSON for API calls or flash+redirect for forms."""
    wants_json = request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html

    if wants_json or request.is_json:
        resp = jsonify(message="Logged out")
    else:
        flash("Logged out", "info")
        resp = redirect(url_for("auth.login"))

    unset_jwt_cookies(resp)
    session.clear()
    return resp


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def forgot_password():
    form = RequestResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user:
            token_value = generate_token({"user_id": str(user.id)}, expires_in=3600)
            reset = PasswordResetToken(
                user_id=user.id,
                token=token_value,
                expires_at=datetime.utcnow() + timedelta(hours=1),
            )
            db.session.add(reset)
            db.session.commit()
            reset_link = url_for("auth.reset_password", token=token_value, _external=True)
            send_email(
                template_name="auth/password_reset",
                recipient=user.email,
                subject="Reset your password",
                context={
                    "user": {"name": user.name or user.username},
                    "reset_link": reset_link,
                    "expires_hours": 1,
                },
                priority="high",
            )
        flash("If that email exists, a reset link was sent", "info")
        return redirect(url_for("auth.login"))
    return render_template("auth/forgot_password.html", form=form)


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def reset_password(token):
    form = ResetPasswordForm()
    reset = PasswordResetToken.query.filter_by(token=token, used=False).first()
    if not reset or reset.expires_at < datetime.utcnow():
        flash("Invalid or expired token", "danger")
        return redirect(url_for("auth.login"))
    user = User.query.get(reset.user_id)
    if not user:
        flash("User not found", "danger")
        return redirect(url_for("auth.login"))
    if form.validate_on_submit():
        if not is_strong_password(form.password.data):
            flash("Password does not meet complexity requirements", "danger")
            return render_template("auth/reset_password.html", form=form)
        user.password_hash = bcrypt.generate_password_hash(form.password.data).decode("utf-8")
        reset.used = True
        db.session.commit()
        try:
            dispatch_notification(
                recipient_id=str(user.id),
                actor_id=None,
                ntype="password_changed",
                reference_id=str(user.id),
                metadata={"event": "password_reset"},
                send_email=False,
            )
        except NotificationError:
            pass
        flash("Password updated", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/reset_password.html", form=form)


@auth_bp.route("/google/login")
def google_login():
    redirect_uri = url_for("auth.google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route("/google/callback")
def google_callback():
    token = oauth.google.authorize_access_token()
    userinfo = token.get("userinfo") or {}
    email = userinfo.get("email")
    sub = userinfo.get("sub")
    name = userinfo.get("name") or ""
    if not email or not sub:
        flash("Invalid Google response", "danger")
        return redirect(url_for("auth.login"))
    oauth_account = OAuthAccount.query.filter_by(provider="google", provider_account_id=sub).first()
    if oauth_account:
        user = User.query.get(oauth_account.user_id)
    else:
        # If a linked account stored email as provider_account_id, upgrade it to the Google sub for future logins
        oauth_account = OAuthAccount.query.filter_by(provider="google", provider_account_id=email.lower()).first()
        if oauth_account:
            oauth_account.provider_account_id = sub
            user = User.query.get(oauth_account.user_id)
            db.session.commit()
        else:
            user = User.query.filter_by(email=email.lower()).first()
            if not user:
                # Use a short random secret to avoid bcrypt's 72-byte input limit
                random_pass = bcrypt.generate_password_hash(secrets.token_urlsafe(32)).decode("utf-8")
                user = User(
                    email=email.lower(),
                    username=email.split("@")[0] + f"_{random.randint(1000,9999)}",
                    name=name or email,
                    password_hash=random_pass,
                    terms_accepted_at=datetime.utcnow(),
                    email_verified=True,
                    is_active=True,
                )
                db.session.add(user)
                db.session.commit()
            oauth_account = OAuthAccount(provider="google", provider_account_id=sub, user_id=user.id)
            db.session.add(oauth_account)
            db.session.commit()
    device_label = (request.user_agent.string or "Unknown device")[:120]
    client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr
    upsert_device_session(user.id, device_label, client_ip)
    access_token = create_access_token(identity=str(user.id), additional_claims={"username": user.username})
    refresh_token = create_refresh_token(identity=str(user.id))
    resp = make_response(redirect(url_for("users.dashboard")))
    set_access_cookies(resp, access_token)
    set_refresh_cookies(resp, refresh_token)
    flash("Logged in with Google", "success")
    return resp
