import uuid
from datetime import datetime
from flask import current_app
from app.extensions import db
from app.models import LiveSession
from app.core.storage import get_s3_client, s3_public_url


def store_replay(session_id: str, file_path: str, mime_type: str) -> str:
    bucket = current_app.config.get("AWS_S3_BUCKET")
    prefix = current_app.config.get("AWS_REPLAY_PREFIX", "replays/")
    key = f"{prefix}{session_id}/{uuid.uuid4().hex}"
    client = get_s3_client()
    client.upload_file(file_path, bucket, key, ExtraArgs={"ContentType": mime_type, "ACL": "public-read"})
    url = s3_public_url(key)
    LiveSession.query.filter_by(id=session_id).update({"replay_url": url, "ended_at": datetime.utcnow(), "is_active": False})
    db.session.commit()
    return url


def generate_signed_replay_url(key: str, expires_in: int = 3600) -> str:
    client = get_s3_client()
    return client.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": current_app.config.get("AWS_S3_BUCKET"), "Key": key},
        ExpiresIn=expires_in,
    )
