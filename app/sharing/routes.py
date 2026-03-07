from flask import render_template, abort
from app.sharing import sharing_bp
from app.models import Post
from .services import twitter_share_url, facebook_share_url, whatsapp_share_url, og_metadata


@sharing_bp.get("/post/<uuid:post_id>")
def view_public(post_id):
    post = Post.query.get(post_id)
    if not post or post.is_archived:
        abort(404)
    meta = og_metadata(post)
    return render_template("sharing/post_public.html", post=post, meta=meta, share_links={
        "twitter": twitter_share_url(post_id),
        "facebook": facebook_share_url(post_id),
        "whatsapp": whatsapp_share_url(post_id),
    })
