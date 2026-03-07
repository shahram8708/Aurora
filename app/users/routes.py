import uuid
from datetime import datetime
from flask import render_template, flash, redirect, url_for, request, current_app, abort, session
from flask_jwt_extended import jwt_required, get_jwt_identity, unset_jwt_cookies
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlalchemy import or_
from app.extensions import db, limiter, csrf
from app.models import (
    User,
    BioLink,
    Block,
    Restrict,
    Mute,
    CloseFriend,
    Follow,
    FollowRequest,
    Notification,
    Story,
    StoryHighlight,
    StoryHighlightItem,
    LiveSession,
    Post,
    Reel,
)
from app.users.forms import ProfileUpdateForm, PrivacyForm, ProfessionalForm
from app.core.security import validate_image, unique_s3_key
from app.core.storage import upload_profile_image, delete_profile_image
from app.notifications.notification_dispatcher import dispatch_notification
from app.notifications.notification_service import NotificationError
from app.monetization.monetization_service import (
    get_subscription_status as monetization_subscription_status,
    get_subscriber_content_selection,
)
from app.settings.services import get_or_create_settings
from app.stories.services import can_view_story
from . import users_bp


def _current_user():
    identity = get_jwt_identity()
    try:
        user = User.query.get(uuid.UUID(str(identity)))
        if not user or not user.is_active or user.is_deleted:
            return None
        return user
    except (TypeError, ValueError):
        return None


def _active_user_or_404(user_id):
    return User.query.filter_by(id=user_id, is_active=True, is_deleted=False).first_or_404()


def _is_following(viewer_id, target_id) -> bool:
    if not viewer_id or not target_id:
        return False
    return bool(Follow.query.filter_by(follower_id=viewer_id, following_id=target_id).first())


def _is_blocked_either(a_id, b_id) -> bool:
    if not a_id or not b_id:
        return False
    return bool(
        Block.query.filter(
            or_(
                (Block.user_id == a_id) & (Block.target_id == b_id),
                (Block.user_id == b_id) & (Block.target_id == a_id),
            )
        ).first()
    )


def _can_view_relationships(viewer_id, target: User) -> bool:
    if not target.is_private:
        return True
    if viewer_id and str(viewer_id) == str(target.id):
        return True
    return _is_following(viewer_id, target.id)


def _follow_request_status(viewer_id, target_id):
    if not viewer_id or not target_id:
        return None
    req = FollowRequest.query.filter_by(requester_id=viewer_id, target_id=target_id, status="pending").first()
    if req:
        return "pending"
    return None


def _incoming_follow_request(viewer_id, target_id):
    if not viewer_id or not target_id:
        return None
    return FollowRequest.query.filter_by(requester_id=target_id, target_id=viewer_id, status="pending").first()


def _serialize_story(story: Story) -> dict:
    return {
        "id": str(story.id),
        "media_type": story.story_type,
        "media_url": story.media_url,
        "caption": story.text_content,
        "created_at": story.created_at.isoformat() if story.created_at else "",
        "username": story.user.username if story.user else None,
        "cover_url": story.thumbnail_url or story.media_url,
    }


def _serialize_highlights(user_id, story_list, user_profile_photo):
    if not story_list:
        return []
    story_index = {str(s.id): idx for idx, s in enumerate(story_list)}
    highlights = (
        StoryHighlight.query.options(selectinload(StoryHighlight.items).selectinload(StoryHighlightItem.story))
        .filter_by(user_id=user_id)
        .all()
    )
    payload = []
    for hl in highlights:
        items_sorted = sorted(hl.items or [], key=lambda i: i.created_at or datetime.min, reverse=True)
        first_story = next((it.story for it in items_sorted if it.story), None)
        start_idx = story_index.get(str(first_story.id), 0) if first_story else 0
        cover = hl.cover_image or (first_story.thumbnail_url if first_story else None) or (first_story.media_url if first_story else None) or user_profile_photo
        payload.append(
            {
                "id": hl.id,
                "title": hl.title,
                "cover": cover,
                "start_index": start_idx,
                "story_ids": [str(it.story_id) for it in items_sorted if it.story_id],
            }
        )
    return payload


@users_bp.route("/")
def home():
    return redirect(url_for("feed.home"))


@users_bp.route("/dashboard")
@jwt_required()
def dashboard():
    user = _current_user()
    return render_template("dashboard.html", user=user)


@users_bp.route("/profile")
@jwt_required()
def profile():
    user = _current_user()
    live_sessions = (
        LiveSession.query.filter_by(host_id=user.id, is_active=True)
        .order_by(LiveSession.started_at.desc())
        .all()
        if user
        else []
    )
    stories = (
        Story.query.options(selectinload(Story.user))
        .filter(Story.user_id == user.id, Story.expires_at > datetime.utcnow())
        .order_by(Story.created_at.desc())
        .all()
        if user
        else []
    )
    stories_data = [_serialize_story(s) for s in stories if can_view_story(s.user_id, user.id if user else None, s)]
    highlights_data = _serialize_highlights(user.id, stories, user.profile_photo_url if user else None) if user else []
    posts_data = (
        Post.query.filter_by(user_id=user.id, is_archived=False).order_by(Post.created_at.desc()).all()
        if user
        else []
    )
    archived_posts_data = (
        Post.query.filter_by(user_id=user.id, is_archived=True).order_by(Post.created_at.desc()).all()
        if user
        else []
    )
    reels_data = user.reels.order_by(Reel.created_at.desc()).all() if user else []
    subscriber_locks = get_subscriber_content_selection(str(user.id)) if user else {"plan_id": None, "posts": [], "reels": []}
    return render_template(
        "profile/view.html",
        user=user,
        is_owner=True,
        is_following=False,
        viewer_authenticated=True,
        can_view_lists=True,
        can_view_private=True,
        live_sessions=live_sessions,
        stories_data=stories_data,
        highlights_data=highlights_data,
        posts_data=posts_data,
        archived_posts_data=archived_posts_data,
        reels_data=reels_data,
        subscriber_locks=subscriber_locks,
        has_subscription_plan=bool(subscriber_locks.get("plan_id")),
        is_subscriber=True,
    )


@users_bp.route("/profile/<uuid:user_id>")
@jwt_required(optional=True)
def view_profile(user_id):
    viewer_id = get_jwt_identity()
    viewer = _current_user()
    target = _active_user_or_404(user_id)
    # Block hard gate: mimic Instagram "not available" behaviour
    if viewer and _is_blocked_either(viewer.id, target.id):
        abort(404)
    is_owner = str(viewer_id) == str(target.id) if viewer_id else False
    is_following = _is_following(viewer.id if viewer else None, target.id) if not is_owner else False
    can_view_lists = _can_view_relationships(viewer.id if viewer else None, target)
    can_view_private = (not target.is_private) or is_owner or is_following
    follow_request_status = _follow_request_status(viewer.id if viewer else None, target.id) if not is_following else None
    incoming_request = _incoming_follow_request(viewer.id if viewer else None, target.id)
    pending_requests = []
    if is_owner:
        pending_requests = (
            FollowRequest.query.filter_by(target_id=target.id, status="pending")
            .order_by(FollowRequest.created_at.desc())
            .limit(50)
            .all()
        )
    stories = (
        Story.query.options(selectinload(Story.user))
        .filter(Story.user_id == target.id, Story.expires_at > datetime.utcnow())
        .order_by(Story.created_at.desc())
        .all()
        if can_view_private
        else []
    )
    stories = [s for s in stories if can_view_story(s.user_id, viewer_id, s)]
    live_sessions = (
        LiveSession.query.filter_by(host_id=target.id, is_active=True)
        .order_by(LiveSession.started_at.desc())
        .all()
        if (is_owner or is_following)
        else []
    )
    stories_data = [_serialize_story(s) for s in stories]
    highlights_data = _serialize_highlights(target.id, stories, target.profile_photo_url) if can_view_private else []
    posts_data = (
        Post.query.filter_by(user_id=target.id, is_archived=False).order_by(Post.created_at.desc()).all()
        if can_view_private
        else []
    )
    archived_posts_data = (
        Post.query.filter_by(user_id=target.id, is_archived=True).order_by(Post.created_at.desc()).all()
        if is_owner
        else []
    )
    reels_data = target.reels.order_by(Reel.created_at.desc()).all() if can_view_private else []
    subscriber_locks = get_subscriber_content_selection(str(target.id))
    has_subscription_plan = bool(subscriber_locks.get("plan_id"))
    locked_post_ids = set(subscriber_locks.get("posts") or [])
    locked_reel_ids = set(subscriber_locks.get("reels") or [])
    is_subscriber = False
    if viewer_id and has_subscription_plan and not is_owner:
        status = monetization_subscription_status(viewer_id, str(target.id))
        is_subscriber = bool(status and status.get("status") in ("active", "created"))
    if not is_owner and has_subscription_plan and not is_subscriber:
        posts_data = [p for p in posts_data if str(p.id) not in locked_post_ids]
        reels_data = [r for r in reels_data if str(r.id) not in locked_reel_ids]
    # Relationship toggles for safety/controls
    is_blocked = False
    is_restricted = False
    is_muted = False
    is_close_friend = False
    if viewer:
        is_blocked = bool(Block.query.filter_by(user_id=viewer.id, target_id=target.id).first())
        is_restricted = bool(Restrict.query.filter_by(user_id=viewer.id, target_id=target.id).first())
        is_muted = bool(Mute.query.filter_by(user_id=viewer.id, target_id=target.id).first())
        is_close_friend = bool(CloseFriend.query.filter_by(user_id=viewer.id, target_id=target.id).first())
    return render_template(
        "profile/view.html",
        user=target,
        is_owner=is_owner,
        is_following=is_following,
        viewer_authenticated=bool(viewer_id),
        can_view_lists=can_view_lists,
        can_view_private=can_view_private,
        live_sessions=live_sessions,
        follow_request_status=follow_request_status,
        incoming_request=incoming_request,
        pending_requests=pending_requests,
        stories_data=stories_data,
        highlights_data=highlights_data,
        posts_data=posts_data,
        archived_posts_data=archived_posts_data,
        reels_data=reels_data,
        subscriber_locks=subscriber_locks,
        has_subscription_plan=has_subscription_plan,
        is_subscriber=is_subscriber or is_owner,
        is_blocked=is_blocked,
        is_restricted=is_restricted,
        is_muted=is_muted,
        is_close_friend=is_close_friend,
    )


@users_bp.post("/profile/<uuid:user_id>/follow")
@csrf.exempt
@jwt_required()
def follow_user(user_id):
    viewer = _current_user()
    target = _active_user_or_404(user_id)
    if str(viewer.id) == str(target.id):
        abort(400)
    if _is_blocked_either(viewer.id, target.id):
        flash("You can't follow this user", "danger")
        return redirect(request.referrer or url_for("users.view_profile", user_id=target.id))
    already_following = _is_following(viewer.id, target.id)
    if target.is_private and not already_following:
        req = FollowRequest.query.filter_by(requester_id=viewer.id, target_id=target.id).first()
        if not req:
            db.session.add(FollowRequest(requester_id=viewer.id, target_id=target.id, status="pending"))
        else:
            req.status = "pending"
        db.session.commit()
        try:
            current_app.logger.info("Dispatching follow_request notification", extra={
                "recipient_id": str(target.id),
                "actor_id": str(viewer.id),
            })
            dispatch_notification(
                recipient_id=str(target.id),
                actor_id=str(viewer.id),
                ntype="follow_request",
                reference_id=str(target.id),
                metadata={"requester_id": str(viewer.id)},
            )
        except NotificationError:
            current_app.logger.warning("follow_request notification failed", exc_info=e)
    else:
        if not already_following:
            db.session.add(Follow(follower_id=viewer.id, following_id=target.id))
            target.follower_count = max(0, (target.follower_count or 0) + 1)
            viewer.following_count = max(0, (viewer.following_count or 0) + 1)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
            else:
                try:
                    dispatch_notification(
                        recipient_id=str(target.id),
                        actor_id=str(viewer.id),
                        ntype="follow",
                        reference_id=str(target.id),
                        metadata={"follower_id": str(viewer.id)},
                        dedup_key=f"follow:{target.id}",
                    )
                except NotificationError:
                    pass
    return redirect(request.referrer or url_for("users.view_profile", user_id=target.id))


@users_bp.post("/profile/<uuid:user_id>/cancel-request")
@csrf.exempt
@jwt_required()
def cancel_follow_request(user_id):
    viewer = _current_user()
    target = _active_user_or_404(user_id)
    if str(viewer.id) == str(target.id):
        abort(400)
    if _is_blocked_either(viewer.id, target.id):
        return redirect(request.referrer or url_for("users.view_profile", user_id=target.id))
    deleted = (
        FollowRequest.query.filter_by(requester_id=viewer.id, target_id=target.id, status="pending").delete()
    )
    if deleted:
        Notification.query.filter_by(
            recipient_id=target.id,
            actor_id=viewer.id,
            type="follow_request",
        ).delete()
        db.session.commit()
        flash("Follow request cancelled", "info")
    return redirect(request.referrer or url_for("users.view_profile", user_id=target.id))


@users_bp.post("/profile/<uuid:user_id>/unfollow")
@csrf.exempt
@jwt_required()
def unfollow_user(user_id):
    viewer = _current_user()
    target = _active_user_or_404(user_id)
    if str(viewer.id) == str(target.id):
        abort(400)
    if _is_blocked_either(viewer.id, target.id):
        return redirect(request.referrer or url_for("users.view_profile", user_id=target.id))
    deleted = Follow.query.filter_by(follower_id=viewer.id, following_id=target.id).delete()
    if deleted:
        target.follower_count = max(0, (target.follower_count or 0) - 1)
        viewer.following_count = max(0, (viewer.following_count or 0) - 1)
        db.session.commit()
    return redirect(request.referrer or url_for("users.view_profile", user_id=target.id))


@users_bp.post("/profile/requests/<int:req_id>/accept")
@csrf.exempt
@jwt_required()
def accept_follow_request(req_id):
    viewer = _current_user()
    req = FollowRequest.query.get_or_404(req_id)
    if str(req.target_id) != str(viewer.id):
        abort(403)
    if _is_blocked_either(req.target_id, req.requester_id):
        abort(403)
    # Create follow if not already
    requester = User.query.get(req.requester_id)
    if not _is_following(req.requester_id, req.target_id):
        db.session.add(Follow(follower_id=req.requester_id, following_id=req.target_id))
        viewer.follower_count = max(0, (viewer.follower_count or 0) + 1)
        if requester:
            requester.following_count = max(0, (requester.following_count or 0) + 1)
    # Optionally auto-follow back (mutual) to mirror Instagram-like mutual state
    if requester and not _is_following(req.target_id, req.requester_id):
        db.session.add(Follow(follower_id=req.target_id, following_id=req.requester_id))
        requester.follower_count = max(0, (requester.follower_count or 0) + 1)
        viewer.following_count = max(0, (viewer.following_count or 0) + 1)
    db.session.delete(req)
    db.session.commit()
    try:
        dispatch_notification(
            recipient_id=str(req.requester_id),
            actor_id=str(viewer.id),
            ntype="follow_approved",
            reference_id=str(req.requester_id),
            metadata={"target_id": str(viewer.id)},
        )
    except NotificationError:
        pass
    return redirect(request.referrer or url_for("users.profile"))


@users_bp.post("/profile/requests/<int:req_id>/decline")
@csrf.exempt
@jwt_required()
def decline_follow_request(req_id):
    viewer = _current_user()
    req = FollowRequest.query.get_or_404(req_id)
    if str(req.target_id) != str(viewer.id):
        abort(403)
    if _is_blocked_either(req.target_id, req.requester_id):
        abort(403)
    db.session.delete(req)
    db.session.commit()
    return redirect(request.referrer or url_for("users.profile"))


@users_bp.route("/profile/<uuid:user_id>/followers")
@jwt_required(optional=True)
def followers(user_id):
    viewer = _current_user()
    target = _active_user_or_404(user_id)
    if viewer and _is_blocked_either(viewer.id, target.id):
        abort(404)
    can_view = _can_view_relationships(viewer.id if viewer else None, target)
    users = []
    if can_view:
        users = (
            User.query.join(Follow, Follow.follower_id == User.id)
            .filter(Follow.following_id == target.id)
            .filter(User.is_active.is_(True))
            .order_by(User.username.asc())
            .limit(200)
            .all()
        )
    return render_template(
        "profile/follow_list.html",
        target=target,
        users=users,
        list_type="followers",
        can_view=can_view,
    )


@users_bp.route("/profile/<uuid:user_id>/following")
@jwt_required(optional=True)
def following(user_id):
    viewer = _current_user()
    target = _active_user_or_404(user_id)
    if viewer and _is_blocked_either(viewer.id, target.id):
        abort(404)
    can_view = _can_view_relationships(viewer.id if viewer else None, target)
    users = []
    if can_view:
        users = (
            User.query.join(Follow, Follow.following_id == User.id)
            .filter(Follow.follower_id == target.id)
            .filter(User.is_active.is_(True))
            .order_by(User.username.asc())
            .limit(200)
            .all()
        )
    return render_template(
        "profile/follow_list.html",
        target=target,
        users=users,
        list_type="following",
        can_view=can_view,
    )


@users_bp.route("/profile/edit", methods=["GET", "POST"])
@csrf.exempt  # Skip Flask-WTF CSRF; JWT cookie auth still required
@jwt_required(locations=["cookies"])  # Use access token from cookies
@limiter.limit("5 per minute")
def edit_profile():
    user = _current_user()
    form = ProfileUpdateForm()
    if request.method == "GET":
        form.username.data = user.username
        form.name.data = user.name
        form.bio.data = user.bio
        form.gender.data = user.gender
        form.is_private.data = user.is_private
        form.is_professional.data = user.is_professional
        form.category.data = user.category
        form.contact_email.data = user.contact_email
        form.contact_phone.data = user.contact_phone
        form.address.data = user.address
        while len(form.links.entries):
            form.links.pop_entry()
        for link in user.bio_links[: form.links.max_entries]:
            entry = form.links.append_entry()
            entry.form.label.data = link.label
            entry.form.url.data = link.url
        while len(form.links.entries) < form.links.min_entries:
            form.links.append_entry()
    if form.validate_on_submit():
        if form.username.data.lower() != user.username:
            if User.query.filter(User.username == form.username.data.lower(), User.id != user.id).first():
                flash("Username already taken", "danger")
                return render_template("profile/edit.html", form=form, user=user)
            user.username = form.username.data.lower()
        user.name = form.name.data
        user.bio = form.bio.data
        user.gender = form.gender.data
        user.is_private = form.is_private.data
        user.is_professional = form.is_professional.data
        user.category = form.category.data
        user.contact_email = form.contact_email.data
        user.contact_phone = form.contact_phone.data
        user.address = form.address.data
        if form.profile_photo.data:
            valid, filename = validate_image(form.profile_photo.data)
            if not valid:
                flash(filename, "danger")
                return render_template("profile/edit.html", form=form, user=user)
            key = unique_s3_key(str(user.id), filename)
            url = upload_profile_image(str(user.id), form.profile_photo.data, key)
            delete_profile_image(user.profile_photo_url)
            user.profile_photo_url = url
        BioLink.query.filter_by(user_id=user.id).delete()
        for link_form in form.links.entries:
            if link_form.form.url.data and link_form.form.label.data:
                db.session.add(
                    BioLink(user_id=user.id, label=link_form.form.label.data, url=link_form.form.url.data)
                )
        try:
            db.session.commit()
            flash("Profile updated", "success")
            return redirect(url_for("users.profile"))
        except IntegrityError:
            db.session.rollback()
            flash("Duplicate link detected", "danger")
    else:
        if request.method == "POST":
            # Log validation errors and submitted data to help debug failed submissions
            current_app.logger.warning("Profile update failed validation", extra={"errors": form.errors, "data": request.form})
            print("PROFILE_EDIT_DEBUG", {"errors": form.errors, "data": request.form})
            flash("Could not update profile. Please fix the errors below.", "danger")
    return render_template("profile/edit.html", form=form, user=user)


@users_bp.route("/settings")
@jwt_required()
def settings():
    user = _current_user()
    privacy_form = PrivacyForm(obj=user)
    professional_form = ProfessionalForm(obj=user)
    settings = get_or_create_settings(user.id) if user else None
    return render_template(
        "settings/settings.html",
        user=user,
        settings=settings,
        privacy_form=privacy_form,
        professional_form=professional_form,
    )


@users_bp.route("/settings/privacy", methods=["POST"])
@jwt_required()
@limiter.limit("5 per minute")
def update_privacy():
    user = _current_user()
    form = PrivacyForm()
    if form.validate_on_submit():
        user.is_private = form.is_private.data
        db.session.commit()
        flash("Privacy updated", "success")
    return redirect(url_for("users.settings"))


@users_bp.route("/settings/professional", methods=["POST"])
@jwt_required()
@limiter.limit("5 per minute")
def update_professional():
    user = _current_user()
    form = ProfessionalForm()
    if form.validate_on_submit():
        user.is_professional = form.is_professional.data
        user.category = form.category.data
        db.session.commit()
        flash("Professional settings updated", "success")
    return redirect(url_for("users.settings"))


@users_bp.route("/settings/deactivate", methods=["POST"])
@jwt_required()
def deactivate_account():
    user = _current_user()
    if not user:
        abort(404)
    user.is_active = False
    db.session.commit()
    flash("Account deactivated. Log in anytime to reactivate.", "warning")
    resp = redirect(url_for("auth.login"))
    unset_jwt_cookies(resp)
    session.clear()
    return resp


@users_bp.route("/settings/delete", methods=["POST"])
@jwt_required()
def delete_account():
    user = _current_user()
    if not user:
        abort(404)
    # Remove the user entirely; ON DELETE CASCADE on related tables cleans up dependent records.
    db.session.delete(user)
    db.session.commit()
    flash("Account deleted permanently", "warning")
    resp = redirect(url_for("auth.login"))
    unset_jwt_cookies(resp)
    session.clear()
    return resp


@users_bp.route("/relationships/safety-center")
@jwt_required()
def safety_center():
    user = _current_user()
    if not user:
        abort(401)
    blocked = (
        db.session.query(Block, User)
        .join(User, Block.target_id == User.id)
        .filter(Block.user_id == user.id)
        .order_by(Block.created_at.desc())
        .all()
    )
    restricted = (
        db.session.query(Restrict, User)
        .join(User, Restrict.target_id == User.id)
        .filter(Restrict.user_id == user.id)
        .order_by(Restrict.created_at.desc())
        .all()
    )
    muted = (
        db.session.query(Mute, User)
        .join(User, Mute.target_id == User.id)
        .filter(Mute.user_id == user.id)
        .order_by(Mute.created_at.desc())
        .all()
    )
    return render_template(
        "relationships/safety_center.html",
        user=user,
        blocked=blocked,
        restricted=restricted,
        muted=muted,
    )


@users_bp.route("/relationships/block/<uuid:target_id>", methods=["POST"])
@jwt_required()
@limiter.limit("10 per minute")
def block_user(target_id):
    user = _current_user()
    if str(user.id) == str(target_id):
        flash("Cannot block yourself", "danger")
        return redirect(request.referrer or url_for("users.profile"))
    if not User.query.get(target_id):
        flash("User not found", "danger")
        return redirect(request.referrer or url_for("users.profile"))
    exists = Block.query.filter_by(user_id=user.id, target_id=target_id).first()
    if not exists:
        db.session.add(Block(user_id=user.id, target_id=target_id))
        # Sever relationships to mirror real-world block behaviour
        removed_a = Follow.query.filter_by(follower_id=user.id, following_id=target_id).delete(synchronize_session=False)
        removed_b = Follow.query.filter_by(follower_id=target_id, following_id=user.id).delete(synchronize_session=False)
        FollowRequest.query.filter(
            (FollowRequest.requester_id == user.id) & (FollowRequest.target_id == target_id)
            | (FollowRequest.requester_id == target_id) & (FollowRequest.target_id == user.id)
        ).delete(synchronize_session=False)
        CloseFriend.query.filter(
            (CloseFriend.user_id == user.id) & (CloseFriend.target_id == target_id)
            | (CloseFriend.user_id == target_id) & (CloseFriend.target_id == user.id)
        ).delete(synchronize_session=False)
        Restrict.query.filter(
            (Restrict.user_id == user.id) & (Restrict.target_id == target_id)
            | (Restrict.user_id == target_id) & (Restrict.target_id == user.id)
        ).delete(synchronize_session=False)
        Mute.query.filter(
            (Mute.user_id == user.id) & (Mute.target_id == target_id)
            | (Mute.user_id == target_id) & (Mute.target_id == user.id)
        ).delete(synchronize_session=False)
        # Adjust counters based on removed follows
        tgt = User.query.get(target_id)
        if removed_a and tgt:
            tgt.follower_count = max(0, (tgt.follower_count or 0) - removed_a)
        if removed_b:
            user.following_count = max(0, (user.following_count or 0) - removed_b)
        db.session.commit()
        flash("User blocked", "success")
    return redirect(request.referrer or url_for("users.profile"))


@users_bp.route("/relationships/unblock/<uuid:target_id>", methods=["POST"])
@jwt_required()
def unblock_user(target_id):
    user = _current_user()
    Block.query.filter_by(user_id=user.id, target_id=target_id).delete()
    db.session.commit()
    flash("User unblocked", "success")
    return redirect(request.referrer or url_for("users.profile"))


@users_bp.route("/relationships/restrict/<uuid:target_id>", methods=["POST"])
@jwt_required()
def restrict_user(target_id):
    user = _current_user()
    if str(user.id) == str(target_id):
        flash("Cannot restrict yourself", "danger")
        return redirect(request.referrer or url_for("users.profile"))
    if not Restrict.query.filter_by(user_id=user.id, target_id=target_id).first():
        db.session.add(Restrict(user_id=user.id, target_id=target_id))
        db.session.commit()
    flash("User restricted", "success")
    return redirect(request.referrer or url_for("users.profile"))


@users_bp.route("/relationships/unrestrict/<uuid:target_id>", methods=["POST"])
@jwt_required()
def unrestrict_user(target_id):
    user = _current_user()
    Restrict.query.filter_by(user_id=user.id, target_id=target_id).delete()
    db.session.commit()
    flash("User unrestricted", "success")
    return redirect(request.referrer or url_for("users.profile"))


@users_bp.route("/relationships/mute/<uuid:target_id>", methods=["POST"])
@jwt_required()
def mute_user(target_id):
    user = _current_user()
    if str(user.id) == str(target_id):
        flash("Cannot mute yourself", "danger")
        return redirect(request.referrer or url_for("users.profile"))
    if not Mute.query.filter_by(user_id=user.id, target_id=target_id).first():
        db.session.add(Mute(user_id=user.id, target_id=target_id))
        db.session.commit()
    flash("User muted", "success")
    return redirect(request.referrer or url_for("users.profile"))


@users_bp.route("/relationships/unmute/<uuid:target_id>", methods=["POST"])
@jwt_required()
def unmute_user(target_id):
    user = _current_user()
    Mute.query.filter_by(user_id=user.id, target_id=target_id).delete()
    db.session.commit()
    flash("User unmuted", "success")
    return redirect(request.referrer or url_for("users.profile"))


@users_bp.route("/relationships/close-friend/<uuid:target_id>", methods=["POST"])
@jwt_required()
def add_close_friend(target_id):
    user = _current_user()
    if str(user.id) == str(target_id):
        flash("Cannot add yourself", "danger")
        return redirect(request.referrer or url_for("users.profile"))
    if not CloseFriend.query.filter_by(user_id=user.id, target_id=target_id).first():
        db.session.add(CloseFriend(user_id=user.id, target_id=target_id))
        db.session.commit()
    flash("Added to close friends", "success")
    return redirect(request.referrer or url_for("users.profile"))


@users_bp.route("/relationships/remove-close-friend/<uuid:target_id>", methods=["POST"])
@jwt_required()
def remove_close_friend(target_id):
    user = _current_user()
    CloseFriend.query.filter_by(user_id=user.id, target_id=target_id).delete()
    db.session.commit()
    flash("Removed from close friends", "success")
    return redirect(request.referrer or url_for("users.profile"))
