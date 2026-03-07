import hashlib
import os
import shlex
import subprocess
import tempfile
import uuid
from datetime import datetime
from typing import Any
from flask import current_app
from werkzeug.utils import secure_filename
from app.core.storage import get_s3_client, s3_public_url


class VideoValidationError(ValueError):
    pass


def _run(cmd: list[str]):
    try:
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, text=True)
    except FileNotFoundError as exc:
        missing = cmd[0] if cmd else "binary"
        raise VideoValidationError(f"Required tool not found: {missing}. Install FFmpeg/FFprobe or set FFMPEG_BIN/FFPROBE_BIN.") from exc
    if process.returncode != 0:
        raise VideoValidationError(process.stderr.strip() or "FFmpeg command failed")
    return process.stdout


def validate_video_file(file_storage) -> str:
    mime = file_storage.mimetype or ""
    if mime not in current_app.config["REEL_ALLOWED_MIME"]:
        raise VideoValidationError("Only MP4 uploads are allowed")
    size = file_storage.content_length or 0
    if size > current_app.config["REEL_MAX_SIZE_MB"] * 1024 * 1024:
        raise VideoValidationError("Video exceeds size limit")
    filename = secure_filename(file_storage.filename or "reel.mp4")
    if not filename.lower().endswith(".mp4"):
        raise VideoValidationError("File must be mp4")
    return filename


def store_temp(file_storage, suffix: str | None = None) -> str:
    name = file_storage.filename or "temp.bin"
    ext = os.path.splitext(name)[1] or suffix or ".bin"
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext)
    with os.fdopen(tmp_fd, "wb") as fh:
        file_storage.stream.seek(0)
        fh.write(file_storage.read())
    return tmp_path


def hash_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe_video(path: str) -> dict[str, Any]:
    ffprobe = current_app.config.get("FFPROBE_BIN", "ffprobe")
    cmd = [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,duration", "-of", "json", path]
    out = _run(cmd)
    import json as _json

    data = _json.loads(out)
    stream = (data.get("streams") or [{}])[0]
    duration = float(stream.get("duration") or 0)
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    if duration <= 0 or width <= 0 or height <= 0:
        raise VideoValidationError("Unable to read video metadata")
    if duration > current_app.config["REEL_MAX_DURATION_SEC"]:
        raise VideoValidationError("Video too long")
    return {"duration": duration, "width": width, "height": height}


def probe_audio(path: str) -> float:
    ffprobe = current_app.config.get("FFPROBE_BIN", "ffprobe")
    cmd = [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
    out = _run(cmd)
    try:
        return float(out.strip())
    except ValueError as exc:  # pragma: no cover - guard against bad probe
        raise VideoValidationError("Invalid voiceover file") from exc


def generate_thumbnail(path: str) -> str:
    thumb_path = tempfile.mktemp(suffix=".jpg")
    ffmpeg = current_app.config.get("FFMPEG_BIN", "ffmpeg")
    cmd = [ffmpeg, "-y", "-ss", "0.5", "-i", path, "-frames:v", "1", "-q:v", "2", thumb_path]
    _run(cmd)
    return thumb_path


def compress_video(src: str, speed_factor: float) -> str:
    out_path = tempfile.mktemp(suffix=".mp4")
    ffmpeg = current_app.config.get("FFMPEG_BIN", "ffmpeg")
    speed_filter = f"setpts={1/ max(speed_factor, 0.1):.3f}*PTS" if speed_factor and speed_factor != 1 else "setpts=PTS"
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        src,
        "-vf",
        f"{speed_filter},scale='min(1080,iw)':-2",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "23",
        "-movflags",
        "+faststart",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        out_path,
    ]
    _run(cmd)
    return out_path


def merge_voiceover(video_path: str, voice_path: str, mix_ratio: float) -> str:
    out_path = tempfile.mktemp(suffix=".mp4")
    ffmpeg = current_app.config.get("FFMPEG_BIN", "ffmpeg")
    mix = max(0.05, min(mix_ratio or 0.5, 0.95))
    filter_complex = f"[0:a]volume={1-mix}[va];[1:a]volume={mix}[vb];[va][vb]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        video_path,
        "-i",
        voice_path,
        "-filter_complex",
        filter_complex,
        "-map",
        "0:v",
        "-map",
        "[aout]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        out_path,
    ]
    _run(cmd)
    return out_path


def upload_assets(user_id: str, video_path: str, thumb_path: str, voiceover_path: str | None, background_path: str | None) -> dict[str, str]:
    s3 = get_s3_client()
    bucket = current_app.config["AWS_S3_BUCKET"]
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    base = f"users/{user_id}/reels/{stamp}_{uuid.uuid4().hex}"

    def _upload(path: str, suffix: str, content_type: str) -> str:
        key = f"{base}_{suffix}"
        with open(path, "rb") as fh:
            s3.upload_fileobj(fh, bucket, key, ExtraArgs={"ACL": "public-read", "ContentType": content_type})
        return s3_public_url(key)

    video_url = _upload(video_path, "video.mp4", "video/mp4")
    thumb_url = _upload(thumb_path, "thumb.jpg", "image/jpeg")
    voice_url = _upload(voiceover_path, "voiceover.m4a", "audio/mp4") if voiceover_path else None
    bg_url = _upload(background_path, "greenscreen.jpg", "image/jpeg") if background_path else None
    return {"video_url": video_url, "thumbnail_url": thumb_url, "voiceover_url": voice_url, "background_url": bg_url}


def prevent_duplicate(hash_value: str, user_id: str | None = None) -> str:
    scope = user_id or "global"
    key = f"reel:hash:{scope}:{hash_value}"
    added = current_app.redis_client.setnx(key, 1)
    if added:
        current_app.redis_client.expire(key, 600)
    if not added:
        raise VideoValidationError("Duplicate upload detected")
    return key


def validate_voiceover_duration(video_duration: float, voice_duration: float):
    if voice_duration > video_duration + 0.5:
        raise VideoValidationError("Voiceover longer than video")
