import io
import os
import uuid
import tempfile
from datetime import datetime
from typing import Tuple
from PIL import Image, ImageEnhance, ImageFilter
from hachoir.parser import createParser
from hachoir.metadata import extractMetadata
from flask import current_app
from werkzeug.utils import secure_filename
from app.core.storage import get_s3_client, s3_public_url

ALLOWED_IMAGE_MIME = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_VIDEO_MIME = {"video/mp4", "video/quicktime"}
MAX_FILES = 10
MAX_IMAGE_SIZE_MB = 12
MAX_VIDEO_SIZE_MB = 50
MAX_VIDEO_DURATION_SEC = 120


def _unique_key(user_id: str, prefix: str, filename: str) -> str:
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    safe = secure_filename(filename)
    return f"users/{user_id}/{prefix}_{stamp}_{uuid.uuid4().hex}_{safe}"


def process_image(file_storage, brightness: float, contrast: float, crop_box: tuple | None, image_filter: str) -> tuple[bytes, bytes, int, int]:
    image = Image.open(file_storage.stream).convert("RGB")
    if crop_box:
        image = image.crop(crop_box)
    if brightness and brightness > 0:
        image = ImageEnhance.Brightness(image).enhance(brightness)
    if contrast and contrast > 0:
        image = ImageEnhance.Contrast(image).enhance(contrast)
    if image_filter == "blur":
        image = image.filter(ImageFilter.GaussianBlur(radius=1.2))
    elif image_filter == "sharpen":
        image = image.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
    elif image_filter == "grayscale":
        image = image.convert("L").convert("RGB")

    max_side = 2048
    w, h = image.size
    if max(w, h) > max_side:
        scale = max_side / float(max(w, h))
        image = image.resize((int(w * scale), int(h * scale)))
    buf = io.BytesIO()
    image.save(buf, format="JPEG", optimize=True, quality=88)
    buf.seek(0)

    thumb = image.copy()
    thumb.thumbnail((400, 400))
    thumb_buf = io.BytesIO()
    thumb.save(thumb_buf, format="JPEG", optimize=True, quality=80)
    thumb_buf.seek(0)
    return buf.read(), thumb_buf.read(), image.width, image.height


def process_video(file_storage) -> tuple[str, float, int, int]:
    # Persist to disk for hachoir parsing
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        file_storage.save(tmp.name)
        path = tmp.name

    parser = createParser(path)
    if not parser:
        os.remove(path)
        raise ValueError("Unable to read video metadata")

    with parser:
        metadata = extractMetadata(parser)

    if not metadata:
        os.remove(path)
        raise ValueError("Unable to read video metadata")

    duration = 0
    width = 0
    height = 0

    duration_item = metadata.get("duration") if hasattr(metadata, "get") else None
    if duration_item and getattr(duration_item, "value", None) is not None:
        dur_val = duration_item.value
        if hasattr(dur_val, "total_seconds"):
            duration = dur_val.total_seconds()
        else:
            try:
                duration = float(dur_val)
            except Exception:
                duration = 0

    width_item = metadata.get("width") if hasattr(metadata, "get") else None
    if width_item and getattr(width_item, "value", None) is not None:
        try:
            width = int(width_item.value)
        except Exception:
            width = 0

    height_item = metadata.get("height") if hasattr(metadata, "get") else None
    if height_item and getattr(height_item, "value", None) is not None:
        try:
            height = int(height_item.value)
        except Exception:
            height = 0

    if duration and duration > MAX_VIDEO_DURATION_SEC:
        os.remove(path)
        raise ValueError("Video too long")

    return path, duration, width, height


def upload_media(user_id: str, file_storage, brightness: float, contrast: float, crop_box: tuple | None, image_filter: str):
    bucket = current_app.config["AWS_S3_BUCKET"]
    s3 = get_s3_client()
    mime = file_storage.mimetype or ""
    if mime in ALLOWED_IMAGE_MIME:
        processed_bytes, thumb_bytes, width, height = process_image(file_storage, brightness, contrast, crop_box, image_filter)
        key = _unique_key(user_id, "post_img", file_storage.filename)
        thumb_key = _unique_key(user_id, "post_thumb", file_storage.filename)
        s3.put_object(Body=processed_bytes, Bucket=bucket, Key=key, ContentType="image/jpeg", ACL="public-read")
        s3.put_object(Body=thumb_bytes, Bucket=bucket, Key=thumb_key, ContentType="image/jpeg", ACL="public-read")
        url = s3_public_url(key)
        thumb_url = s3_public_url(thumb_key)
        return {
            "media_type": "image",
            "media_url": url,
            "thumbnail_url": thumb_url,
            "width": width,
            "height": height,
            "duration": None,
        }
    if mime in ALLOWED_VIDEO_MIME:
        if file_storage.content_length and file_storage.content_length > MAX_VIDEO_SIZE_MB * 1024 * 1024:
            raise ValueError("Video exceeds size limit")
        path, duration, width, height = process_video(file_storage)
        key = _unique_key(user_id, "post_vid", file_storage.filename)
        try:
            with open(path, "rb") as fh:
                s3.upload_fileobj(
                    fh,
                    bucket,
                    key,
                    ExtraArgs={"ContentType": mime, "ACL": "public-read"},
                )
        finally:
            if os.path.exists(path):
                os.remove(path)

        url = s3_public_url(key)
        return {
            "media_type": "video",
            "media_url": url,
            "thumbnail_url": None,
            "width": width,
            "height": height,
            "duration": duration,
        }
    raise ValueError("Unsupported media type")


def validate_media_files(files: list) -> None:
    if not files or len(files) == 0:
        raise ValueError("At least one media file required")
    if len(files) > MAX_FILES:
        raise ValueError("Too many files")
    for f in files:
        if not f or not getattr(f, "filename", None):
            raise ValueError("Invalid file")
        mime = f.mimetype or ""
        size = f.content_length or 0
        if mime in ALLOWED_IMAGE_MIME:
            if size > MAX_IMAGE_SIZE_MB * 1024 * 1024:
                raise ValueError("Image exceeds size limit")
        elif mime in ALLOWED_VIDEO_MIME:
            if size > MAX_VIDEO_SIZE_MB * 1024 * 1024:
                raise ValueError("Video exceeds size limit")
        else:
            raise ValueError("Unsupported media type")
