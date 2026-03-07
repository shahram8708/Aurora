import os
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv
from flask import Flask, jsonify, request, g, send_from_directory, url_for
import uuid
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from .config import get_config
from .extensions import db, migrate, bcrypt, csrf, jwt, limiter, socketio, mail, oauth, init_redis_client, init_celery, celery
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from .models import User
from .core.errors import build_error_response, register_error_handlers
from .core.security import apply_security_headers

BASE_DIR = Path(__file__).resolve().parent.parent
# Load environment variables from project root so config picks them up everywhere (app, Celery, CLI).
# override=True ensures local .env values win over shell defaults when developing on Windows.
load_dotenv(BASE_DIR / ".env", override=True)


def create_app(env: str | None = None):
    app = Flask(__name__)
    env_name = env or os.environ.get("FLASK_ENV", "development")
    app.config.from_object(get_config(env_name))

    # Enable CORS for API use-cases; tightened origins should be configured via ENV.
    CORS(app, supports_credentials=True)

    register_extensions(app)
    register_blueprints(app)
    register_socket_namespaces()
    register_error_handlers(app)
    register_middlewares(app)
    register_local_upload_routes(app)
    configure_logging(app)

    # Ensure a usable admin account exists for the panel when ENV values are provided.
    with app.app_context():
        from .security.rbac_service import bootstrap_default_admin

        bootstrap_default_admin()

    @app.route("/health")
    def health():
        return jsonify(status="ok"), 200

    # Global exception guard to avoid leaking stack traces
    @app.errorhandler(Exception)
    def handle_unexpected(error):
        app.logger.exception("Unhandled exception")
        status = error.code if isinstance(error, HTTPException) else 500
        message = getattr(error, "description", "Internal server error")
        if app.debug:
            message = f"{message}: {error}"
        template = f"errors/{status}.html" if status in (403, 404, 500) else "errors/500.html"
        return build_error_response(status, message, template)

    return app


def register_extensions(app: Flask):
    db.init_app(app)
    migrate.init_app(app, db)
    bcrypt.init_app(app)
    csrf.init_app(app)
    jwt.init_app(app)
    from flask import redirect, flash, url_for
    from flask_jwt_extended import unset_jwt_cookies

    @jwt.expired_token_loader
    def handle_expired(jwt_header, jwt_payload):
        flash("Session expired. Please log in again.", "warning")
        resp = redirect(url_for("auth.login"))
        unset_jwt_cookies(resp)
        return resp

    @jwt.unauthorized_loader
    def handle_missing(reason):
        if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
            return jsonify({"msg": "login_required"}), 401
        flash("Please log in to continue.", "warning")
        resp = redirect(url_for("auth.login"))
        unset_jwt_cookies(resp)
        return resp

    @jwt.invalid_token_loader
    def handle_invalid(reason):
        if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
            return jsonify({"msg": "invalid_token"}), 401
        flash("Session invalid. Please log in again.", "warning")
        resp = redirect(url_for("auth.login"))
        unset_jwt_cookies(resp)
        return resp
    use_redis = app.config.get("USE_REDIS", True)
    if use_redis:
        app.config.setdefault("RATELIMIT_STORAGE_URL", app.config["REDIS_URL"])
    else:
        app.config.pop("RATELIMIT_STORAGE_URL", None)
    limiter._default_limits = app.config["RATE_LIMIT_DEFAULT"].split(";") if app.config.get("RATE_LIMIT_DEFAULT") else []
    limiter.init_app(app)
    mail.init_app(app)
    oauth.init_app(app)
    oauth.register(
        name="google",
        client_id=app.config["GOOGLE_CLIENT_ID"],
        client_secret=app.config["GOOGLE_CLIENT_SECRET"],
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    app.redis_client = init_redis_client(app.config.get("REDIS_URL"), enabled=use_redis)
    socketio_queue = app.config.get("REDIS_URL") if use_redis else None
    socketio.init_app(app, message_queue=socketio_queue, logger=False, engineio_logger=False)
    init_celery(app)


def register_blueprints(app: Flask):
    from .auth.routes import auth_bp
    from .users.routes import users_bp
    from .posts import posts_bp
    from .engagement import engagement_bp
    from .feed import feed_bp
    from .reels import reels_bp
    from .stories import stories_bp
    from .recommendation import recommendation_bp
    from .messaging import messaging_bp
    from .notifications import notifications_bp
    from .broadcast import broadcast_bp
    from .sharing import sharing_bp
    from .explore import explore_bp
    from .algorithms import algorithms_bp
    from .moderation import moderation_bp
    from .live import live_bp
    from .business import business_bp
    from .monetization import monetization_bp
    from .payments import payments_bp
    from .shop import shop_bp
    from .commerce import commerce_bp
    from .orders import orders_bp
    from .affiliate import affiliate_bp
    from .admin import admin_bp
    from .security import security_bp
    from .settings import settings_bp
    from .system import system_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(posts_bp)
    app.register_blueprint(engagement_bp)
    app.register_blueprint(feed_bp)
    app.register_blueprint(reels_bp)
    app.register_blueprint(stories_bp)
    app.register_blueprint(recommendation_bp)
    app.register_blueprint(messaging_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(broadcast_bp)
    app.register_blueprint(sharing_bp)
    app.register_blueprint(explore_bp)
    app.register_blueprint(algorithms_bp)
    app.register_blueprint(moderation_bp)
    app.register_blueprint(live_bp)
    app.register_blueprint(business_bp)
    app.register_blueprint(monetization_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(shop_bp)
    app.register_blueprint(commerce_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(affiliate_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(security_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(system_bp)

    # Initialize algorithm listeners (search indexing, etc.)
    from .algorithms import listeners  # noqa: F401


def register_middlewares(app: Flask):
    from .security.rbac_service import load_current_admin
    from .security.audit_log_service import audit_admin_action

    @app.before_request
    def attach_admin():
        load_current_admin()

    @app.before_request
    def load_request_user():
        g.current_user = None
        try:
            verify_jwt_in_request(optional=True)
            identity = get_jwt_identity()
        except Exception:
            identity = None
        if identity:
            try:
                g.current_user = User.query.get(uuid.UUID(str(identity)))
            except Exception:
                g.current_user = None

    @app.context_processor
    def inject_current_user():
        user = getattr(g, "current_user", None)
        anonymous = type("AnonymousUser", (), {"is_authenticated": False})()
        preview = []

        def notification_link(n):
            try:
                ntype = (getattr(n, "type", "") or "").lower()
                meta = getattr(n, "meta", {}) or {}
                actor_id = getattr(n, "actor_id", None)
                ref_id = getattr(n, "reference_id", None)

                post_id = meta.get("post_id") or (ref_id if "post" in ntype else None)
                reel_id = meta.get("reel_id") or (ref_id if "reel" in ntype else None)
                story_id = meta.get("story_id")
                session_id = meta.get("session_id")
                order_id = meta.get("order_id") or (ref_id if ntype.startswith("order_") else None)
                conversation_id = meta.get("conversation_id")
                comment_id = meta.get("comment_id")
                profile_target = meta.get("requester_id") or meta.get("target_id") or actor_id or ref_id

                if ntype in {"follow_request", "follow", "follow_approved"} and profile_target:
                    return url_for("users.view_profile", user_id=profile_target)

                if ntype in {"like_post", "like_comment", "comment_post", "reply_comment", "mention_post", "mention_comment", "tag_post"} and post_id:
                    link = url_for("posts.view_post", post_id=post_id)
                    if comment_id:
                        return f"{link}#comment-{comment_id}"
                    return link

                if ntype in {"like_reel"} and reel_id:
                    return url_for("reels.detail", reel_id=reel_id)

                if ntype in {"story_reply", "tag_story", "story_like"} and story_id:
                    return url_for("stories.viewer", story_id=story_id)

                if ntype in {"dm", "message_request", "group_added"}:
                    if conversation_id:
                        return url_for("messaging.view_conversation", conversation_id=conversation_id)
                    return url_for("messaging.inbox")

                if ntype.startswith("payment_") or ntype in {"order_confirmed", "shipment_sent", "delivery_completed", "refund_processed"}:
                    if order_id:
                        # History page is HTML; tracking endpoint is JSON, so default to history for consistency.
                        return url_for("orders.history")
                    return url_for("orders.history")

                if ntype in {"live_started", "live_reminder"} and session_id:
                    return url_for("live.view_live", session_id=session_id)

                if ntype in {"login_new_device", "password_changed", "account_suspended", "account_restored", "report_resolved", "copyright_strike"}:
                    return url_for("users.settings")

                return url_for("notifications.notifications_page")
            except Exception as e:
                app.logger.warning("notification_link_failed", exc_info=e)
                return url_for("notifications.notifications_page")

        def notification_text(n):
            try:
                ntype = (getattr(n, "type", "") or "").lower()
                meta = getattr(n, "meta", {}) or {}
                actor = meta.get("actor_name") or meta.get("username") or meta.get("sender_name")
                someone = actor or "Someone"
                agg = getattr(n, "aggregated_count", 1) or 1
                amount = meta.get("amount")
                purpose = meta.get("purpose")
                device = meta.get("device") or meta.get("user_agent")

                if ntype == "follow_request":
                    return f"{someone} sent you a follow request"
                if ntype == "follow":
                    return f"{someone} started following you"
                if ntype == "follow_approved":
                    return f"{someone} accepted your follow request"
                if ntype == "like_post":
                    return f"{someone} liked your post" + (f" ({agg})" if agg > 1 else "")
                if ntype == "comment_post":
                    return f"{someone} commented on your post"
                if ntype == "reply_comment":
                    return f"{someone} replied to your comment"
                if ntype in {"mention_post", "mention_comment"}:
                    return f"{someone} mentioned you"
                if ntype in {"dm", "message_request"}:
                    return f"{someone} sent you a message"
                if ntype == "payment_success":
                    label = "Payment received"
                    if purpose:
                        label = f"{label} for {purpose}"
                    if amount:
                        label = f"{label} - Amount: {amount}"
                    return label
                if ntype == "payment_failed":
                    return "Payment failed - check details"
                if ntype == "login_new_device":
                    return f"New login from {device}" if device else "New login detected"
                if ntype == "password_changed":
                    return "Your password was changed"

                label = (ntype.replace("_", " ") or "notification").title()
                if agg > 1:
                    label = f"{label} ({agg})"
                return label
            except Exception as e:
                app.logger.warning("notification_text_failed", exc_info=e)
                return "Notification"

        if user and getattr(user, "is_authenticated", False):
            try:
                from .models.notification import Notification

                preview = (
                    Notification.query.filter_by(recipient_id=user.id)
                    .order_by(Notification.created_at.desc())
                    .limit(5)
                    .all()
                )
            except Exception as e:
                app.logger.warning("notification_preview_failed", exc_info=e)
        return {
            "current_user": user or anonymous,
            "notifications_preview": preview,
            "notification_link": notification_link,
            "notification_text": notification_text,
        }

    @app.after_request
    def secure_headers(response):
        response = apply_security_headers(response)
        audit_admin_action(response)
        return response


def register_local_upload_routes(app: Flask):
    # Serve locally stored uploads when AWS is disabled or credentials are missing (local fallback).
    missing_creds = not (app.config.get("AWS_ACCESS_KEY_ID") and app.config.get("AWS_SECRET_ACCESS_KEY"))
    use_local = not app.config.get("USE_AWS", True) or missing_creds
    if not use_local:
        return

    storage_root = app.config.get("LOCAL_STORAGE_PATH", "local_uploads")
    if not os.path.isabs(storage_root):
        storage_root = BASE_DIR / storage_root
    storage_root = Path(storage_root)
    storage_root.mkdir(parents=True, exist_ok=True)

    base_url = app.config.get("LOCAL_STORAGE_BASE_URL", "/static/uploads").rstrip("/")
    base_url = base_url if base_url.startswith("/") else f"/{base_url}"

    @app.route(f"{base_url}/<path:key>")
    def serve_local_uploads(key: str):
        return send_from_directory(storage_root, key)


def configure_logging(app: Flask):
    log_dir = app.config["LOG_DIR"]
    os.makedirs(log_dir, exist_ok=True)

    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

    app_handler = RotatingFileHandler(app.config["APP_LOG_PATH"], maxBytes=5 * 1024 * 1024, backupCount=5)
    app_handler.setLevel(app.config["LOG_LEVEL"])
    app_handler.setFormatter(fmt)
    app.logger.addHandler(app_handler)

    security_handler = RotatingFileHandler(app.config["SECURITY_LOG_PATH"], maxBytes=5 * 1024 * 1024, backupCount=5)
    security_handler.setLevel(logging.WARNING)
    security_handler.setFormatter(fmt)
    logging.getLogger("security").addHandler(security_handler)

    audit_handler = RotatingFileHandler(app.config["AUDIT_LOG_PATH"], maxBytes=5 * 1024 * 1024, backupCount=5)
    audit_handler.setLevel(logging.INFO)
    audit_handler.setFormatter(fmt)
    logging.getLogger("audit").addHandler(audit_handler)

    metrics_handler = RotatingFileHandler(app.config["METRICS_LOG_PATH"], maxBytes=5 * 1024 * 1024, backupCount=3)
    metrics_handler.setLevel(logging.INFO)
    metrics_handler.setFormatter(fmt)
    logging.getLogger("metrics").addHandler(metrics_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(app.config["LOG_LEVEL"])
    stream_handler.setFormatter(fmt)
    app.logger.addHandler(stream_handler)
    app.logger.setLevel(app.config["LOG_LEVEL"])


def register_socket_namespaces():
    # Import namespaces to register handlers
    from .messaging import socket_events  # noqa: F401
    from .notifications import socket_events as notif_socket  # noqa: F401
    from .live import socket_events as live_socket  # noqa: F401
