import uuid
from flask import jsonify, request, render_template, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.orm import joinedload
from app.extensions import limiter
from app.models import Post, Comment, Save, User, ReelSave, Reel
from . import engagement_bp
from .services import (
    toggle_like,
    add_comment,
    delete_comment,
    pin_comment,
    toggle_save,
    create_story_share,
    create_direct_share,
)


@engagement_bp.before_request
def _debug_engagement_request():
    # Debug logging to confirm requests reach the blueprint
    current_app.logger.info(
        "engagement request",
        extra={"path": request.path, "method": request.method, "content_type": request.content_type},
    )
    print("[engagement] incoming", request.method, request.path)


def _as_uuid(val):
    return val if isinstance(val, uuid.UUID) else uuid.UUID(str(val))


def _json_error(message: str, status: int = 400):
    return jsonify({"error": message}), status


@engagement_bp.post("/like/<uuid:post_id>")
@jwt_required()
@limiter.limit("30 per minute")
def like_post(post_id):
    post = Post.query.get_or_404(_as_uuid(post_id))
    user_id = get_jwt_identity()
    count, liked = toggle_like(user_id, str(post.id))
    return jsonify({"liked": liked, "like_count": count})


@engagement_bp.post("/save/<uuid:post_id>")
@jwt_required()
@limiter.limit("30 per minute")
def save_post(post_id):
    Post.query.get_or_404(_as_uuid(post_id))
    user_id = get_jwt_identity()
    saved = toggle_save(user_id, str(post_id))
    return jsonify({"saved": saved})


@engagement_bp.get("/saved")
@jwt_required()
def saved_posts():
    user_id = get_jwt_identity()
    user_uuid = _as_uuid(user_id)
    post_saves = (
        Save.query.options(joinedload(Save.post).joinedload(Post.media))
        .filter(Save.user_id == user_uuid)
        .order_by(Save.created_at.desc())
        .all()
    )
    reel_saves = (
        ReelSave.query.options(joinedload(ReelSave.reel).joinedload(Reel.user))
        .filter(ReelSave.user_id == user_uuid)
        .order_by(ReelSave.created_at.desc())
        .all()
    )
    posts = [s.post for s in post_saves if s.post]
    reels = [s.reel for s in reel_saves if s.reel]
    return render_template("saved.html", posts=posts, reels=reels)


@engagement_bp.post("/comment/<uuid:post_id>")
@jwt_required()
@limiter.limit("20 per minute")
def create_comment(post_id):
    post = Post.query.get_or_404(_as_uuid(post_id))
    data = request.get_json(force=True, silent=True) or {}
    content = (data.get("content") or "").strip()
    parent_id = data.get("parent_id")
    parent_comment = None
    if parent_id is not None:
        try:
            parent_id = int(parent_id)
        except (TypeError, ValueError):
            return _json_error("Invalid parent_id")
        parent_comment = Comment.query.filter_by(id=parent_id, post_id=post.id).first()
        if not parent_comment:
            return _json_error("Invalid parent comment")
        if parent_comment.parent_comment_id:
            return _json_error("Reply depth limit reached")
    if not content or len(content) > 1000:
        return _json_error("Invalid content")
    comment = add_comment(get_jwt_identity(), str(post_id), content, parent_comment.id if parent_comment else None)
    return jsonify({
        "id": comment.id,
        "content": comment.content,
        "parent_id": comment.parent_comment_id,
        "created_at": comment.created_at.isoformat(),
    })


@engagement_bp.delete("/comment/<int:comment_id>")
@jwt_required()
@limiter.limit("20 per minute")
def remove_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    user_id = get_jwt_identity()
    current_app.logger.info("delete_comment request", extra={"comment_id": comment_id, "user_id": str(user_id), "comment_user_id": str(comment.user_id), "post_owner_id": str(comment.post.user_id)})
    print("[engagement] delete_comment request", {"comment_id": comment_id, "user_id": str(user_id)})
    try:
        delete_comment(user_id, comment)
    except PermissionError:
        current_app.logger.warning("delete_comment forbidden", extra={"comment_id": comment_id, "user_id": str(user_id)})
        print("[engagement] delete_comment forbidden", {"comment_id": comment_id, "user_id": str(user_id)})
        return jsonify({"error": "Forbidden"}), 403
    current_app.logger.info("delete_comment success", extra={"comment_id": comment_id, "user_id": str(user_id)})
    print("[engagement] delete_comment success", {"comment_id": comment_id, "user_id": str(user_id)})
    return jsonify({"deleted": True})


@engagement_bp.post("/comment/<int:comment_id>/pin")
@jwt_required()
@limiter.limit("10 per minute")
def toggle_pin_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    user_id = get_jwt_identity()
    current_app.logger.info("pin_comment request", extra={"comment_id": comment_id, "user_id": str(user_id), "post_owner_id": str(comment.post.user_id)})
    print("[engagement] pin_comment request", {"comment_id": comment_id, "user_id": str(user_id)})
    try:
        pin_comment(user_id, comment)
    except PermissionError:
        current_app.logger.warning("pin_comment forbidden", extra={"comment_id": comment_id, "user_id": str(user_id)})
        print("[engagement] pin_comment forbidden", {"comment_id": comment_id, "user_id": str(user_id)})
        return jsonify({"error": "Forbidden"}), 403
    current_app.logger.info("pin_comment success", extra={"comment_id": comment_id, "user_id": str(user_id), "pinned": comment.is_pinned})
    print("[engagement] pin_comment success", {"comment_id": comment_id, "user_id": str(user_id), "pinned": comment.is_pinned})
    return jsonify({"pinned": comment.is_pinned})


@engagement_bp.post("/share/story/<uuid:post_id>")
@jwt_required()
@limiter.limit("10 per minute")
def share_story(post_id):
    Post.query.get_or_404(_as_uuid(post_id))
    try:
        share, story = create_story_share(get_jwt_identity(), str(post_id))
    except ValueError:
        return _json_error("Post not found", 404)
    except Exception:
        current_app.logger.exception("Failed to share post to story", extra={"post_id": str(post_id)})
        return _json_error("Unable to share right now", 503)
    return jsonify({"share_id": share.id, "story_id": str(story.id)})


@engagement_bp.post("/share/dm/<uuid:post_id>")
@jwt_required()
@limiter.limit("10 per minute")
def share_dm(post_id):
    Post.query.get_or_404(_as_uuid(post_id))
    sender_id = get_jwt_identity()
    data = request.get_json(force=True, silent=True) or {}
    receiver_username = data.get("receiver")
    if not receiver_username:
        return _json_error("Receiver required")
    receiver = User.query.filter_by(username=receiver_username.lower()).first()
    if not receiver:
        return _json_error("User not found", 404)
    if str(receiver.id) == str(sender_id):
        return _json_error("Cannot share to yourself")
    try:
        share = create_direct_share(sender_id, str(receiver.id), str(post_id))
    except Exception:
        current_app.logger.exception("Failed to share post via DM", extra={"post_id": str(post_id), "receiver": receiver_username})
        return _json_error("Unable to share right now", 503)
    return jsonify({"share_id": share.id})
