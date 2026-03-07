import mimetypes
from urllib.parse import urlparse

ALLOWED_VOICE_MIME = {"audio/mpeg", "audio/mp4", "audio/aac", "audio/wav", "audio/ogg"}
ALLOWED_FILE_MIME = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/zip",
    "application/x-7z-compressed",
    "text/plain",
    "image/png",
    "image/jpeg",
    "image/gif",
    "video/mp4",
}
DANGEROUS_EXTENSIONS = {"exe", "bat", "cmd", "sh", "js", "jar", "msi"}
ALLOWED_GIF_DOMAINS = {"giphy.com", "media.giphy.com", "tenor.com", "media.tenor.com", "g.tenor.com"}
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024
MAX_VOICE_SIZE_BYTES = 10 * 1024 * 1024
MAX_VIDEO_SIZE_BYTES = 50 * 1024 * 1024
ALLOWED_VIDEO_MIME = {"video/mp4", "video/quicktime"}


def validate_file(filename: str, mime: str, size: int) -> None:
    ext = (filename.rsplit(".", 1)[-1] or "").lower() if "." in filename else ""
    if ext in DANGEROUS_EXTENSIONS:
        raise ValueError("Unsupported file type")
    if mime not in ALLOWED_FILE_MIME:
        raise ValueError("Unsupported MIME type")
    if size > MAX_FILE_SIZE_BYTES:
        raise ValueError("File too large")


def validate_voice(filename: str, mime: str, size: int) -> None:
    if mime not in ALLOWED_VOICE_MIME:
        raise ValueError("Unsupported voice MIME")
    if size > MAX_VOICE_SIZE_BYTES:
        raise ValueError("Voice file too large")


def validate_video(filename: str, mime: str, size: int) -> None:
    if mime not in ALLOWED_VIDEO_MIME:
        raise ValueError("Unsupported video MIME")
    if size > MAX_VIDEO_SIZE_BYTES:
        raise ValueError("Video too large")


def sniff_mime(filename: str) -> str | None:
    mime, _ = mimetypes.guess_type(filename)
    return mime


def validate_gif_url(url: str) -> None:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if hostname not in ALLOWED_GIF_DOMAINS and not hostname.endswith(".tenor.com") and not hostname.endswith(".giphy.com"):
        raise ValueError("Unsupported GIF source")


def validate_gif_provider(provider: str) -> None:
    if provider.lower() not in {"giphy", "tenor"}:
        raise ValueError("Unsupported GIF provider")
