from datetime import datetime, timedelta
import html
import uuid
from sqlalchemy import func
from app.notifications.notification_dispatcher import dispatch_notification
from app.notifications.notification_service import NotificationError
from sqlalchemy.orm import selectinload
from app.extensions import db
from app.models import Like, Comment, Save, Post, StoryShare, DirectShare, Story, StoryInsight


def _post_uuid(val):
    return val if isinstance(val, uuid.UUID) else uuid.UUID(str(val))


def _user_uuid(val):
    return val if isinstance(val, uuid.UUID) else uuid.UUID(str(val))


def toggle_like(user_id: str, post_id: str) -> tuple[int, bool]:
    post_uuid = _post_uuid(post_id)
    user_uuid = _user_uuid(user_id)
    post = Post.query.get(post_uuid)
    owner_id = str(post.user_id) if post else None
    existing = Like.query.filter_by(user_id=user_uuid, post_id=post_uuid).first()
    if existing:
        db.session.delete(existing)
        liked = False
    else:
        db.session.add(Like(user_id=user_uuid, post_id=post_uuid))
        liked = True
    db.session.commit()
    count = db.session.query(func.count(Like.id)).filter_by(post_id=post_uuid).scalar()
    if liked and owner_id and owner_id != str(user_id):
        try:
            dispatch_notification(
                recipient_id=owner_id,
                actor_id=str(user_uuid),
                ntype="like_post",
                reference_id=str(post_uuid),
                metadata={"post_id": str(post_uuid)},
            )
        except NotificationError:
            pass
    return count, liked


def toggle_save(user_id: str, post_id: str) -> bool:
    post_uuid = _post_uuid(post_id)
    user_uuid = _user_uuid(user_id)
    existing = Save.query.filter_by(user_id=user_uuid, post_id=post_uuid).first()
    if existing:
        db.session.delete(existing)
        saved = False
    else:
        db.session.add(Save(user_id=user_uuid, post_id=post_uuid))
        saved = True
    db.session.commit()
    return saved


def add_comment(user_id: str, post_id: str, content: str, parent_id: int | None = None) -> Comment:
    post_uuid = _post_uuid(post_id)
    user_uuid = _user_uuid(user_id)
    sanitized = html.escape(content.strip())
    comment = Comment(user_id=user_uuid, post_id=post_uuid, content=sanitized, parent_comment_id=parent_id)
    db.session.add(comment)
    db.session.commit()
    post = Post.query.get(post_uuid)
    owner_id = str(post.user_id) if post else None
    try:
        if parent_id:
            parent = Comment.query.get(parent_id)
            if parent and str(parent.user_id) != str(user_id):
                dispatch_notification(
                    recipient_id=str(parent.user_id),
                    actor_id=user_id,
                    ntype="reply_comment",
                    reference_id=str(parent_id),
                    metadata={"post_id": str(post_uuid), "comment_id": comment.id},
                )
        elif owner_id and owner_id != str(user_id):
            dispatch_notification(
                recipient_id=owner_id,
                actor_id=str(user_uuid),
                ntype="comment_post",
                reference_id=str(post_uuid),
                metadata={"post_id": str(post_uuid), "comment_id": comment.id},
                dedup_key=f"comment:{post_uuid}",
            )
    except NotificationError:
        pass
    return comment


def delete_comment(user_id: str, comment: Comment):
    if str(comment.user_id) != str(user_id) and str(comment.post.user_id) != str(user_id):
        raise PermissionError("Not allowed")
    db.session.delete(comment)
    db.session.commit()


def pin_comment(user_id: str, comment: Comment):
    if str(comment.post.user_id) != str(user_id):
        raise PermissionError("Not allowed")
    comment.is_pinned = not comment.is_pinned
    db.session.commit()


def _share_post_to_story(user_id: str, post: Post) -> Story:
    """Create a 24h story using the first media (or caption) from the post."""
    media_url = None
    thumb_url = None
    story_type = "text"
    if post.media:
        first_media = sorted(post.media, key=lambda m: m.order_index)[0]
        media_url = first_media.media_url
        thumb_url = first_media.thumbnail_url or (first_media.media_url if first_media.media_type == "image" else None)
        story_type = "photo" if first_media.media_type == "image" else "video"
    expires_at = datetime.utcnow() + timedelta(hours=24)
    story = Story(
        user_id=_user_uuid(user_id),
        media_url=media_url,
        thumbnail_url=thumb_url,
        text_content=(post.caption or "")[:500],
        story_type=story_type,
        is_close_friends=False,
        expires_at=expires_at,
    )
    db.session.add(story)
    db.session.flush()
    db.session.add(StoryInsight(story_id=story.id))
    return story


def create_story_share(user_id: str, post_id: str) -> tuple[StoryShare, Story]:
    post_uuid = _post_uuid(post_id)
    user_uuid = _user_uuid(user_id)
    post = Post.query.options(selectinload(Post.media)).get(post_uuid)
    if not post:
        raise ValueError("Post not found")
    story = _share_post_to_story(user_id, post)
    share = StoryShare(user_id=user_uuid, post_id=post_uuid)
    db.session.add(share)
    db.session.commit()
    try:
        from app.stories.services import schedule_expiry

        schedule_expiry(str(story.id), story.expires_at)
    except Exception:
        # If scheduling fails, the story still exists; avoid breaking the request.
        pass
    return share, story


def create_direct_share(sender_id: str, receiver_id: str, post_id: str) -> DirectShare:
    post_uuid = _post_uuid(post_id)
    sender_uuid = _user_uuid(sender_id)
    receiver_uuid = _user_uuid(receiver_id)
    share = DirectShare(sender_id=sender_uuid, receiver_id=receiver_uuid, post_id=post_uuid)
    db.session.add(share)
    db.session.commit()
    return share


def load_post_engagement(post_id: str) -> dict:
    post_uuid = _post_uuid(post_id)
    post = (
        Post.query.options(
            selectinload(Post.media),
            selectinload(Post.likes),
            selectinload(Post.comments).selectinload(Comment.replies),
        )
        .filter_by(id=post_uuid)
        .first()
    )
    if not post:
        return {}
    return {
        "likes": len(post.likes),
        "comments": len(post.comments),
    }
