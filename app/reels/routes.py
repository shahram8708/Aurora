from datetime import datetime
import uuid
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import limiter
from app.models import Reel, ReelMusic, ARFilter, User, ReelInsight
from app.recommendation.services import personalized_reels, get_trending_cached, annotate_promoted_reels
from . import reels_bp
from .forms import ReelUploadForm
from .services import create_reel, get_reel, track_view_once, record_watch, get_reel_comments, add_reel_comment, get_reel_likes, add_reel_like, toggle_reel_save
from .analytics import increment_like, increment_share, ensure_insight, _as_uuid


@reels_bp.get("/")
@jwt_required()
def reel_feed():
    user_id = get_jwt_identity()
    user = User.query.get(user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id)))
    reels = personalized_reels(str(user.id), limit=12, offset=0)
    trending = get_trending_cached(limit=10)
    annotate_promoted_reels(trending, viewer_id=user.id)
    return render_template("reels/feed.html", reels=reels, trending=trending)


@reels_bp.route("/create", methods=["GET", "POST"])
@jwt_required()
@limiter.limit("5 per minute")
def create():
    form = ReelUploadForm()
    music_choices = ReelMusic.query.order_by(ReelMusic.title.asc()).all()
    filters = ARFilter.query.order_by(ARFilter.name.asc()).all()
    if request.method == "GET":
        return render_template("reels/create.html", form=form, music_choices=music_choices, filters=filters)
    if form.validate_on_submit():
        user_id = get_jwt_identity()
        user = User.query.get(user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id)))
        try:
            reel = create_reel(
                user,
                form.video.data,
                {
                    "caption": form.caption.data,
                    "music_id": form.music_id.data,
                    "speed_factor": form.speed_factor.data or 1.0,
                    "allow_download": form.allow_download.data,
                    "monetization_enabled": form.monetization_enabled.data,
                    "scheduled_at": form.scheduled_at.data,
                    "text_overlays": form.text_overlays.data,
                    "effects_metadata": form.effects_metadata.data,
                    "stickers_metadata": form.stickers_metadata.data,
                    "is_remix": form.is_remix.data,
                    "original_reel_id": form.original_reel_id.data,
                    "mix_ratio": form.mix_ratio.data,
                    "green_screen_subject_mask": form.green_screen_subject_mask.data,
                    "countdown_seconds": form.countdown_seconds.data,
                    "countdown_autostart": form.countdown_autostart.data,
                    "filter_id": form.filter_id.data,
                },
                voiceover_file=form.voiceover.data,
                background_image=form.background_image.data,
            )
            flash("Reel submitted", "success")
            if reel.is_published:
                return redirect(url_for("reels.reel_feed"))
            flash("Reel scheduled", "info")
            return redirect(url_for("reels.reel_feed"))
        except Exception as exc:  # pylint: disable=broad-except
            flash(str(exc), "danger")
    return render_template("reels/create.html", form=form, music_choices=music_choices, filters=filters)


@reels_bp.get("/<uuid:reel_id>")
@jwt_required()
def detail(reel_id):
    reel = get_reel(reel_id)
    if not reel:
        return render_template("errors/404.html"), 404
    return render_template("reels/detail.html", reel=reel)


@reels_bp.post("/<uuid:reel_id>/view")
@jwt_required()
@limiter.limit("60 per minute")
def view_reel(reel_id):
    track_view_once(str(reel_id), get_jwt_identity())
    return jsonify({"ok": True})


@reels_bp.post("/<uuid:reel_id>/watch")
@jwt_required()
@limiter.limit("120 per minute")
def watch_time(reel_id):
    data = request.get_json(force=True, silent=True) or {}
    seconds = float(data.get("seconds") or 0)
    record_watch(str(reel_id), get_jwt_identity(), seconds)
    return jsonify({"ok": True})


@reels_bp.post("/<uuid:reel_id>/like")
@jwt_required()
@limiter.limit("120 per minute")
def like_reel(reel_id):
    user_id = get_jwt_identity()
    user = User.query.get(user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id)))
    if not user:
        return jsonify({"error": "user_not_found"}), 404
    added = add_reel_like(str(reel_id), user)
    if added:
        increment_like(str(reel_id))
    return jsonify({"liked": True, "already_liked": not added})


@reels_bp.post("/<uuid:reel_id>/share")
@jwt_required()
@limiter.limit("60 per minute")
def share_reel(reel_id):
    increment_share(str(reel_id))
    insight = ensure_insight(str(reel_id))
    # Re-fetch to reflect updated count
    refreshed = ReelInsight.query.filter_by(reel_id=_as_uuid(reel_id)).first()
    share_count = refreshed.share_count if refreshed else getattr(insight, "share_count", 0)
    return jsonify({"shared": True, "share_count": int(share_count or 0)})


@reels_bp.post("/<uuid:reel_id>/save")
@jwt_required()
@limiter.limit("60 per minute")
def save_reel(reel_id):
    user_id = get_jwt_identity()
    try:
        user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
    except (ValueError, AttributeError, TypeError):
        return jsonify({"error": "invalid_user"}), 400
    saved = toggle_reel_save(user_uuid, str(reel_id))
    return jsonify({"saved": saved})


@reels_bp.get("/api/feed")
@jwt_required()
def reel_feed_api():
    user_id = get_jwt_identity()
    user = User.query.get(user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id)))
    if not user:
        return jsonify({"error": "user_not_found"}), 404
    cursor = int(request.args.get("cursor") or 0)
    limit = max(min(int(request.args.get("limit") or 8), 30), 4)
    reels = personalized_reels(str(user.id), limit=limit, offset=cursor)
    html = "".join(render_template("reels/_card.html", reel=reel) for reel in reels)
    next_cursor = cursor + len(reels)
    return jsonify({"html": html, "next_cursor": next_cursor, "has_more": len(reels) == limit})


@reels_bp.get("/<uuid:reel_id>/comments")
@jwt_required()
def list_reel_comments(reel_id):
    comments = get_reel_comments(str(reel_id))
    return jsonify({"comments": comments})


@reels_bp.get("/<uuid:reel_id>/likes")
@jwt_required()
def list_reel_likes(reel_id):
    likes = get_reel_likes(str(reel_id))
    return jsonify({"likes": likes})


@reels_bp.post("/<uuid:reel_id>/comments")
@jwt_required()
def add_comment(reel_id):
    data = request.get_json(force=True, silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "Comment cannot be empty"}), 400
    if len(content) > 400:
        return jsonify({"error": "Comment too long"}), 400
    user_id = get_jwt_identity()
    user = User.query.get(user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id)))
    if not user:
        return jsonify({"error": "user_not_found"}), 404
    comment = add_reel_comment(str(reel_id), user, content)
    return jsonify({"comment": comment})
