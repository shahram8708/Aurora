import re
import mimetypes
from datetime import datetime
from flask import current_app
from werkzeug.utils import secure_filename

ALLOWED_IMAGE_MIME = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def apply_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    additional_sources = current_app.config.get("CSP_ADDITIONAL_SOURCES", "")
    csp_sources = " ".join(additional_sources.split(",")) if additional_sources else ""
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        f"script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://checkout.razorpay.com {csp_sources}; "
        f"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net {csp_sources}; "
        f"img-src 'self' data: https://cdn.jsdelivr.net {csp_sources}; "
        f"font-src 'self' https://fonts.gstatic.com https://fonts.googleapis.com https://cdn.jsdelivr.net {csp_sources}; "
        f"connect-src 'self' https://cdn.jsdelivr.net https://checkout.razorpay.com https://lumberjack.razorpay.com https://api.razorpay.com ws: wss: {csp_sources}; "
        f"frame-src 'self' https://checkout.razorpay.com https://api.razorpay.com {csp_sources}; "
        "frame-ancestors 'self'; "
        "object-src 'none'; "
        "base-uri 'self'"
    )
    if current_app.config.get("HSTS_ENABLED"):
        response.headers["Strict-Transport-Security"] = f"max-age={current_app.config.get('HSTS_MAX_AGE', 31536000)}; includeSubDomains"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    # Third-party widgets like Razorpay checkout are cross-origin; loosen COEP to avoid blocking
    response.headers["Cross-Origin-Embedder-Policy"] = "unsafe-none"
    return response


def is_strong_password(password: str) -> bool:
    return bool(re.match(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{12,}$", password))


def validate_image(file_storage) -> tuple[bool, str]:
    filename = secure_filename(file_storage.filename or "")
    if not filename:
        return False, "Filename required"
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    mime_type, _ = mimetypes.guess_type(filename)
    if f".{ext}" not in ALLOWED_IMAGE_EXT or mime_type not in ALLOWED_IMAGE_MIME:
        return False, "Invalid image type"
    if file_storage.content_length and file_storage.content_length > current_app.config.get("MAX_CONTENT_LENGTH", 0):
        return False, "File too large"
    return True, filename


def unique_s3_key(user_id: str, filename: str) -> str:
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    name = secure_filename(filename)
    return f"users/{user_id}/profile_{timestamp}_{name}"
