import uuid
from flask import render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.orm import selectinload
from app.extensions import limiter, csrf, db
from app.models import (
    Story,
    StoryArchive,
    StoryHighlight,
    StoryHighlightItem,
    StoryLike,
    StoryReply,
    StoryView,
    CloseFriend,
    User,
)
from app.stories.services import create_story_reply, toggle_story_like
from . import stories_bp
from .forms import StoryCreateForm
from .services import (
    create_story,
    register_view,
    register_reply,
    create_highlight,
    add_to_highlight,
    remove_from_highlight,
    get_story_feed_for_viewer,
    can_view_story,
)


@stories_bp.post("/<uuid:story_id>/delete")
@csrf.exempt
@jwt_required()
def delete_story(story_id):
    user_id = get_jwt_identity()
    story = Story.query.get_or_404(story_id)
    if str(story.user_id) != str(user_id):
        return jsonify({"error": "Forbidden"}), 403
    db.session.delete(story)
    db.session.commit()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
        return jsonify({"ok": True})
    flash("Story deleted", "success")
    return redirect(url_for("users.profile"))


@stories_bp.route("/create", methods=["GET", "POST"])
@jwt_required()
@limiter.limit("10 per hour")
def create():
    form = StoryCreateForm()
    if form.validate_on_submit():
        try:
            story = create_story(
                get_jwt_identity(),
                {
                    "story_type": form.story_type.data,
                    "text_content": form.text_content.data,
                    "is_close_friends": form.is_close_friends.data,
                    "stickers": form.stickers.data,
                    "drawing_json": form.drawing_json.data,
                    "link_url": form.link_url.data,
                    "music_id": form.music_id.data,
                },
                file_storage=form.media.data,
            )
            flash("Story posted", "success")
            return redirect(url_for("stories.list_my"))
        except Exception as exc:  # pylint: disable=broad-except
            flash(str(exc), "danger")
    return render_template("stories/create.html", form=form)


@stories_bp.get("/")
@jwt_required()
def list_my():
    user_id = get_jwt_identity()
    stories = get_story_feed_for_viewer(user_id)
    return render_template("stories/list.html", stories=stories, viewer_id=user_id)


@stories_bp.get("/highlights")
@jwt_required()
def highlights():
    user_id = get_jwt_identity()
    user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
    highlights = (
        StoryHighlight.query.options(selectinload(StoryHighlight.items).selectinload(StoryHighlightItem.story))
        .filter_by(user_id=user_uuid)
        .all()
    )
    archives = StoryArchive.query.filter_by(user_id=user_uuid).order_by(StoryArchive.created_at.desc()).all()
    return render_template("stories/highlights.html", highlights=highlights, archives=archives)


@stories_bp.post("/highlights")
@jwt_required()
@limiter.limit("10 per minute")
def create_highlight_route():
    title = (request.form.get("title") or "").strip()
    cover = request.form.get("cover_image")
    if not title:
        flash("Title required", "danger")
        return redirect(url_for("stories.highlights"))
    create_highlight(get_jwt_identity(), title, cover)
    flash("Highlight created", "success")
    return redirect(url_for("stories.highlights"))


@stories_bp.post("/highlights/quick-add")
@csrf.exempt
@jwt_required()
def quick_add_highlight_api():
    """Create a highlight (if needed) and attach a story; returns JSON for UI flows."""
    user_id = get_jwt_identity()
    user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
    data = request.get_json(force=True, silent=True) or request.form or {}
    story_id_raw = (data.get("story_id") or "").strip()
    title = (data.get("title") or "Highlight").strip() or "Highlight"
    cover = data.get("cover_image")
    if not story_id_raw:
        return jsonify({"error": "story_id required"}), 400
    try:
        story_uuid = story_id_raw if isinstance(story_id_raw, uuid.UUID) else uuid.UUID(str(story_id_raw))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid story_id"}), 400
    story = Story.query.get_or_404(story_uuid)
    if str(story.user_id) != str(user_id):
        return jsonify({"error": "Forbidden"}), 403
    highlight = StoryHighlight.query.filter_by(user_id=user_uuid, title=title).first()
    if not highlight:
        fallback_cover = cover or story.thumbnail_url or story.media_url
        highlight = create_highlight(user_uuid, title, fallback_cover)
    elif not highlight.cover_image:
        highlight.cover_image = cover or story.thumbnail_url or story.media_url
        try:
            db.session.commit()
        except Exception:  # noqa: BLE001
            db.session.rollback()
    add_to_highlight(highlight.id, story_uuid)
    return jsonify({"highlight_id": highlight.id, "title": highlight.title})


@stories_bp.post("/highlights/<int:highlight_id>/add")
@jwt_required()
def add_highlight_item(highlight_id):
    story_id_raw = request.form.get("story_id")
    highlight = StoryHighlight.query.get_or_404(highlight_id)
    if str(highlight.user_id) != str(get_jwt_identity()):
        return render_template("errors/403.html"), 403
    if story_id_raw:
        try:
            story_uuid = story_id_raw if isinstance(story_id_raw, uuid.UUID) else uuid.UUID(str(story_id_raw))
        except (TypeError, ValueError):
            return jsonify({"error": "invalid story_id"}), 400
        add_to_highlight(highlight_id, story_uuid)
        # Default cover if missing
        if not highlight.cover_image:
            story = Story.query.get(story_uuid)
            if story:
                highlight.cover_image = story.thumbnail_url or story.media_url
                try:
                    db.session.commit()
                except Exception:  # noqa: BLE001
                    db.session.rollback()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
        return jsonify({"ok": True, "highlight_id": highlight_id})
    return redirect(url_for("stories.highlights"))


@stories_bp.post("/highlights/<int:highlight_id>/delete")
@csrf.exempt
@jwt_required()
def delete_highlight(highlight_id):
    user_id = get_jwt_identity()
    highlight = StoryHighlight.query.get_or_404(highlight_id)
    if str(highlight.user_id) != str(user_id):
        return jsonify({"error": "Forbidden"}), 403
    db.session.delete(highlight)
    db.session.commit()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
        return jsonify({"ok": True})
    flash("Highlight deleted", "success")
    return redirect(url_for("stories.highlights"))


@stories_bp.post("/highlights/item/<int:item_id>/remove")
@jwt_required()
def remove_highlight_item_route(item_id):
    item = StoryHighlightItem.query.get_or_404(item_id)
    highlight = StoryHighlight.query.get(item.highlight_id)
    if highlight and str(highlight.user_id) != str(get_jwt_identity()):
        return render_template("errors/403.html"), 403
    remove_from_highlight(item_id)
    return redirect(url_for("stories.highlights"))


@stories_bp.get("/viewer/<uuid:story_id>")
@jwt_required()
def viewer(story_id):
    story = (
        Story.query.options(
            selectinload(Story.replies).selectinload(StoryReply.user),
            selectinload(Story.likes).selectinload(StoryLike.user),
            selectinload(Story.views).selectinload(StoryView.user),
        )
        .get_or_404(story_id)
    )
    viewer_id = get_jwt_identity()
    if not can_view_story(story.user_id, viewer_id, story):
        return render_template("errors/403.html"), 403
    is_owner = str(viewer_id) == str(story.user_id) if viewer_id else False
    if story.is_close_friends:
        viewer_uuid = viewer_id if isinstance(viewer_id, uuid.UUID) else uuid.UUID(str(viewer_id))
        if not CloseFriend.query.filter_by(user_id=story.user_id, target_id=viewer_uuid).first():
            return render_template("errors/403.html"), 403
    register_view(str(story.id), viewer_id)
    view_count = StoryView.query.filter_by(story_id=story.id).count()
    like_count = StoryLike.query.filter_by(story_id=story.id).count()
    reply_count = StoryReply.query.filter_by(story_id=story.id).count()
    current_app.logger.info(
        "story_view story_id=%s viewer_id=%s views=%s likes=%s replies=%s",
        str(story.id),
        str(viewer_id),
        view_count,
        like_count,
        reply_count,
    )
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return render_template("stories/_viewer_body.html", story=story, is_owner=is_owner, viewer_id=viewer_id)
    return render_template("stories/viewer.html", story=story, is_owner=is_owner, viewer_id=viewer_id)


@stories_bp.post("/<uuid:story_id>/reply")
@csrf.exempt
@jwt_required()
@limiter.limit("30 per minute")
def reply(story_id):
    viewer_id = get_jwt_identity()
    story = Story.query.get_or_404(story_id)
    current_app.logger.info(
        "story_reply_attempt story_id=%s viewer_id=%s path=%s method=%s ua=%s",
        str(story_id),
        str(viewer_id),
        request.path,
        request.method,
        request.headers.get("User-Agent"),
    )
    if not can_view_story(story.user_id, viewer_id, story):
        return jsonify({"error": "Forbidden"}), 403
    data = request.get_json(force=True, silent=True) or {}
    content = (data.get("content") or "").strip()
    current_app.logger.info("story_reply", extra={"story_id": str(story_id), "viewer_id": str(viewer_id), "content_len": len(content)})
    try:
        reply = create_story_reply(str(story_id), viewer_id, content)
    except ValueError as exc:
        current_app.logger.warning("story_reply_invalid", extra={"story_id": str(story_id), "viewer_id": str(viewer_id), "error": str(exc)})
        return jsonify({"error": str(exc)}), 400
    view_count = StoryView.query.filter_by(story_id=story_id).count()
    like_count = StoryLike.query.filter_by(story_id=story_id).count()
    reply_count = StoryReply.query.filter_by(story_id=story_id).count()
    current_app.logger.info(
        "story_reply story_id=%s viewer_id=%s views=%s likes=%s replies=%s",
        str(story_id),
        str(viewer_id),
        view_count,
        like_count,
        reply_count,
    )
    return jsonify(
        {
            "id": reply.id,
            "content": reply.content,
            "user": {
                "id": str(reply.user.id) if reply.user else None,
                "username": reply.user.username if reply.user else None,
            },
            "created_at": reply.created_at.isoformat() if reply.created_at else None,
        }
    )


@stories_bp.post("/<uuid:story_id>/like")
@csrf.exempt
@jwt_required()
@limiter.limit("30 per minute")
def like_story(story_id):
    viewer_id = get_jwt_identity()
    current_app.logger.info(
        "story_like_attempt story_id=%s viewer_id=%s path=%s method=%s ua=%s", 
        str(story_id),
        str(viewer_id),
        request.path,
        request.method,
        request.headers.get("User-Agent"),
    )
    try:
        count, liked = toggle_story_like(str(story_id), viewer_id)
        view_count = StoryView.query.filter_by(story_id=story_id).count()
        reply_count = StoryReply.query.filter_by(story_id=story_id).count()
        current_app.logger.info(
            "story_like story_id=%s viewer_id=%s liked=%s likes=%s views=%s replies=%s",
            str(story_id),
            str(viewer_id),
            liked,
            count,
            view_count,
            reply_count,
        )
        return jsonify({"liked": liked, "like_count": count})
    except Exception as exc:
        current_app.logger.error("story_like_error", exc_info=exc, extra={"story_id": str(story_id), "viewer_id": str(viewer_id)})
        return jsonify({"error": "Unable to like"}), 500


@stories_bp.get("/<uuid:story_id>/metrics")
@csrf.exempt
@jwt_required()
def story_metrics(story_id):
    viewer_id = get_jwt_identity()
    story = (
        Story.query.options(
            selectinload(Story.likes).selectinload(StoryLike.user),
            selectinload(Story.views),
        )
        .filter_by(id=story_id)
        .first_or_404()
    )
    if story.is_close_friends:
        viewer_uuid = viewer_id if isinstance(viewer_id, uuid.UUID) else uuid.UUID(str(viewer_id))
        if not CloseFriend.query.filter_by(user_id=story.user_id, target_id=viewer_uuid).first():
            current_app.logger.warning("story_metrics_forbidden", extra={"story_id": str(story_id), "viewer_id": str(viewer_id)})
            return jsonify({"error": "Forbidden"}), 403
    payload = {
        "like_count": len(story.likes or []),
        "view_count": len(story.views or []),
        "likes": [
            {"id": str(l.user.id), "username": l.user.username} for l in (story.likes or []) if l.user
        ],
    }
    current_app.logger.info(
        "story_metrics story_id=%s viewer_id=%s views=%s likes=%s replies=%s",
        str(story_id),
        str(viewer_id),
        payload["view_count"],
        payload["like_count"],
        StoryReply.query.filter_by(story_id=story_id).count(),
    )
    return jsonify(payload)
