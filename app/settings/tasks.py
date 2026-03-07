import json
import os
import tempfile
import zipfile
from flask import current_app
from app.extensions import celery, db
from app.email.email_service import send_email
from app.models import DataExportJob, User
from app.models.post import Post, PostMedia, Comment
from app.models.messaging import Message
from app.models.commerce import Order, OrderItem
from app.models.payment import PaymentTransaction
from app.core.storage import get_s3_client
import uuid


def _to_uuid(val):
    try:
        return val if isinstance(val, uuid.UUID) else uuid.UUID(str(val))
    except (ValueError, TypeError):
        return None


@celery.task(name="app.settings.tasks.export_user_data")
def export_user_data(job_id: str):
    job_uuid = _to_uuid(job_id)
    if not job_uuid:
        return
    job = DataExportJob.query.get(job_uuid)
    if not job:
        return
    user_id = job.user_id
    payload = {
        "posts": _export_posts(user_id),
        "comments": _export_comments(user_id),
        "messages": _export_messages(user_id),
        "orders": _export_orders(user_id),
        "payments": _export_payments(user_id),
    }
    fd, path = tempfile.mkstemp(prefix="export_", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, indent=2))

    zip_path = f"{path}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(path, arcname="export.json")

    s3 = get_s3_client()
    bucket = current_app.config.get("DATA_EXPORT_BUCKET") or current_app.config.get("AWS_S3_BUCKET")
    key = f"exports/{user_id}/{job.id}.zip"
    s3.upload_file(zip_path, bucket, key, ExtraArgs={"ContentType": "application/zip"})
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=current_app.config["DOWNLOAD_URL_TTL"],
    )
    job.mark_ready(url, current_app.config["DATA_EXPORT_TTL_HOURS"])
    db.session.commit()
    os.remove(path)
    os.remove(zip_path)

    user_uuid = _to_uuid(user_id)
    user = User.query.get(user_uuid)
    if user and user.email:
        send_email(
            template_name="system/data_export_ready",
            recipient=user.email,
            subject="Your data export is ready",
            context={
                "user": {"name": user.name or user.username},
                "download_url": url,
                "expires_hours": current_app.config["DATA_EXPORT_TTL_HOURS"],
            },
            priority="normal",
        )
    return url


def _iso(dt):
    return dt.isoformat() if dt else None


def _export_posts(user_id):
    posts = Post.query.filter_by(user_id=user_id).all()
    result = []
    for p in posts:
        result.append({
            "id": str(p.id),
            "caption": p.caption,
            "created_at": _iso(p.created_at),
            "is_archived": p.is_archived,
            "is_pinned": p.is_pinned,
            "hide_like_count": p.hide_like_count,
            "branded_content_tag": p.branded_content_tag,
            "media": [
                {
                    "type": m.media_type,
                    "url": m.media_url,
                    "thumbnail": m.thumbnail_url,
                    "alt_text": m.alt_text,
                    "order": m.order_index,
                    "width": m.width,
                    "height": m.height,
                    "duration_seconds": m.duration_seconds,
                }
                for m in p.media
            ],
            "hashtags": [h.name for h in p.hashtags],
            "tags": [
                {
                    "user_id": str(t.tagged_user_id),
                    "position_x": t.position_x,
                    "position_y": t.position_y,
                }
                for t in p.tags
            ],
            "likes": len(p.likes),
            "comments_count": len(p.comments),
        })
    return result


def _export_comments(user_id):
    comments = Comment.query.filter_by(user_id=user_id).all()
    return [{
        "id": c.id,
        "post_id": str(c.post_id),
        "content": c.content,
        "parent_comment_id": c.parent_comment_id,
        "is_pinned": c.is_pinned,
        "created_at": _iso(c.created_at),
    } for c in comments]


def _export_messages(user_id):
    msgs = Message.query.filter_by(sender_id=user_id).all()
    return [{
        "id": str(m.id),
        "conversation_id": str(m.conversation_id),
        "type": m.message_type,
        "content": m.content,
        "media_url": m.media_url,
        "media_mime_type": m.media_mime_type,
        "media_size_bytes": m.media_size_bytes,
        "duration_seconds": m.duration_seconds,
        "thumbnail_url": m.thumbnail_url,
        "reply_to_id": str(m.reply_to_id) if m.reply_to_id else None,
        "is_vanish": m.is_vanish,
        "is_deleted": m.is_deleted,
        "gif_provider": m.gif_provider,
        "gif_id": m.gif_id,
        "created_at": _iso(m.created_at),
    } for m in msgs]


def _export_orders(user_id):
    orders = Order.query.filter_by(buyer_id=user_id).all()
    return [{
        "id": str(o.id),
        "total_amount": o.total_amount,
        "currency": o.currency,
        "status": o.status,
        "shipping_address": o.shipping_address_json,
        "created_at": _iso(o.created_at),
        "items": [
            {
                "product_id": str(i.product_id) if i.product_id else None,
                "seller_id": str(i.seller_id) if i.seller_id else None,
                "quantity": i.quantity,
                "price": i.price,
            }
            for i in o.items
        ],
    } for o in orders]


def _export_payments(user_id):
    txns = PaymentTransaction.query.filter_by(user_id=user_id).all()
    return [{
        "id": str(t.id),
        "amount": t.amount,
        "currency": t.currency,
        "purpose": t.purpose,
        "status": t.status,
        "created_at": _iso(t.created_at),
        "razorpay_order_id": t.razorpay_order_id,
        "razorpay_payment_id": t.razorpay_payment_id,
        "failure_reason": t.failure_reason,
        "metadata": t.metadata_json,
    } for t in txns]
