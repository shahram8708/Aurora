from flask import render_template, redirect, url_for, flash, request, jsonify, abort
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import limiter
from app.models import Post
from . import posts_bp
from .forms import PostCreateForm, PostEditForm
from .services import (
    create_post,
    get_post_with_media,
    update_post_caption,
    delete_post,
    toggle_archive as toggle_archive_service,
    toggle_pin,
)
from app.models import Location


@posts_bp.route("/create", methods=["GET", "POST"])
@jwt_required()
@limiter.limit("6 per minute")
def create():
    form = PostCreateForm()
    if form.validate_on_submit():
        files = request.files.getlist(form.media.name)
        try:
            post = create_post(
                get_jwt_identity(),
                files,
                {
                    "caption": form.caption.data,
                    "location_name": form.location_name.data,
                    "location_latitude": form.location_latitude.data,
                    "location_longitude": form.location_longitude.data,
                    "hide_like_count": form.hide_like_count.data,
                    "branded_content_tag": form.branded_content_tag.data,
                    "brightness": form.brightness.data,
                    "contrast": form.contrast.data,
                    "crop_x": form.crop_x.data,
                    "crop_y": form.crop_y.data,
                    "crop_width": form.crop_width.data,
                    "crop_height": form.crop_height.data,
                    "image_filter": form.image_filter.data,
                },
            )
            flash("Post created", "success")
            return redirect(url_for("feed.home"))
        except Exception as exc:  # pylint: disable=broad-except
            flash(str(exc), "danger")
    return render_template("posts/create.html", form=form)


@posts_bp.get("/<uuid:post_id>")
def view_post(post_id):
    post = get_post_with_media(post_id)
    if not post or post.is_archived:
        abort(404)
    return render_template("posts/detail.html", post=post)


@posts_bp.route("/<uuid:post_id>/edit", methods=["GET", "POST"])
@jwt_required()
def edit(post_id):
    post = get_post_with_media(post_id)
    if not post:
        abort(404)
    if str(post.user_id) != str(get_jwt_identity()):
        abort(403)
    form = PostEditForm(obj=post)
    if request.method == "GET" and post.location:
        form.location_name.data = post.location.name
        form.location_latitude.data = post.location.latitude
        form.location_longitude.data = post.location.longitude
    if form.validate_on_submit():
        try:
            update_post_caption(
                get_jwt_identity(),
                post,
                form.caption.data,
                form.branded_content_tag.data,
                form.hide_like_count.data,
                form.location_name.data,
                form.location_latitude.data,
                form.location_longitude.data,
            )
            flash("Post updated", "success")
            return redirect(url_for("feed.home"))
        except PermissionError:
            abort(403)
    return render_template("posts/edit.html", form=form, post=post)


@posts_bp.post("/<uuid:post_id>/delete")
@jwt_required()
@limiter.limit("5 per minute")
def delete_post_route(post_id):
    post = Post.query.get_or_404(post_id)
    try:
        delete_post(get_jwt_identity(), post)
    except PermissionError:
        abort(403)
    flash("Post deleted", "info")
    return redirect(url_for("feed.home"))


@posts_bp.post("/<uuid:post_id>/archive")
@jwt_required()
def archive_post(post_id):
    post = Post.query.get_or_404(post_id)
    try:
        toggle_archive_service(get_jwt_identity(), post)
    except PermissionError:
        abort(403)
    flash("Post archived" if post.is_archived else "Post restored", "success")
    return redirect(url_for("feed.home"))


@posts_bp.post("/<uuid:post_id>/pin")
@jwt_required()
def pin(post_id):
    post = Post.query.get_or_404(post_id)
    try:
        toggle_pin(get_jwt_identity(), post)
    except PermissionError:
        abort(403)
    flash("Post pinned" if post.is_pinned else "Post unpinned", "success")
    return redirect(url_for("feed.home"))


@posts_bp.get("/<uuid:post_id>/snippet")
@jwt_required()
def post_snippet(post_id):
    post = get_post_with_media(post_id)
    if not post:
        abort(404)
    return jsonify({"html": render_template("partials/post_cards.html", posts=[post])})

@posts_bp.get("/locations/search")
@jwt_required()
def search_locations():
    term = (request.args.get("q") or "").strip()
    if not term or len(term) < 2:
        return jsonify([])
    results = Location.query.filter(Location.name.ilike(f"%{term}%")).order_by(Location.name.asc()).limit(8).all()
    return jsonify([{"id": loc.id, "name": loc.name, "lat": loc.latitude, "lng": loc.longitude} for loc in results])
