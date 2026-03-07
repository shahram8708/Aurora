from urllib.parse import quote
from flask import url_for
from app.models import Post


def generate_public_link(post_id: str) -> str:
    return url_for("sharing.view_public", post_id=post_id, _external=True)


def og_metadata(post: Post) -> dict:
    first_media = post.media[0] if post.media else None
    image = first_media.thumbnail_url or first_media.media_url if first_media else None
    return {
        "og:title": post.caption[:60] if post.caption else "Post",
        "og:description": post.caption[:160] if post.caption else "",
        "og:image": image,
        "og:url": generate_public_link(post.id),
    }


def twitter_share_url(post_id: str) -> str:
    link = generate_public_link(post_id)
    return f"https://twitter.com/intent/tweet?url={quote(link)}"


def facebook_share_url(post_id: str) -> str:
    link = generate_public_link(post_id)
    return f"https://www.facebook.com/sharer/sharer.php?u={quote(link)}"


def whatsapp_share_url(post_id: str) -> str:
    link = generate_public_link(post_id)
    return f"https://wa.me/?text={quote(link)}"
