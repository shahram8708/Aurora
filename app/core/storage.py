import os
from pathlib import Path
import boto3
from botocore.exceptions import ClientError
from flask import current_app, request


class LocalS3Client:
    """Minimal S3-like client that writes to disk for dev when USE_AWS is false."""

    def __init__(self, base_path: Path, base_url: str):
        self.base_path = base_path
        self.base_url = base_url.rstrip("/")
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _write(self, key: str, data: bytes):
        target = self.base_path / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def upload_fileobj(self, fileobj, bucket: str, key: str, ExtraArgs=None):  # noqa: ARG002
        data = fileobj.read()
        self._write(key, data)

    def upload_file(self, filename: str, bucket: str, key: str, ExtraArgs=None):  # noqa: ARG002
        data = Path(filename).read_bytes()
        self._write(key, data)

    def put_object(self, Body: bytes, Bucket: str, Key: str, **kwargs):  # noqa: N803, ARG002
        self._write(Key, Body)
        return {"ETag": "local"}

    def delete_object(self, Bucket: str, Key: str):  # noqa: N803, ARG002
        target = self.base_path / Key
        if target.exists():
            target.unlink()
        return {"Deleted": True}

    def generate_presigned_url(self, client_method: str, Params=None, ExpiresIn=3600, HttpMethod=None):  # noqa: ARG002
        key = Params.get("Key") if Params else ""
        return f"{self.base_url}/{key}"


def _local_storage_base_path() -> Path:
    root = current_app.config.get("LOCAL_STORAGE_PATH", "local_uploads")
    if not os.path.isabs(root):
        root = os.path.join(Path(current_app.root_path).parent, root)
    return Path(root)


def _use_local_storage() -> bool:
    cfg = current_app.config
    if not cfg.get("USE_AWS", True):
        return True
    if not cfg.get("AWS_ACCESS_KEY_ID") or not cfg.get("AWS_SECRET_ACCESS_KEY"):
        current_app.logger.info("AWS credentials missing; falling back to local storage")
        return True
    return False


def _public_base_url() -> str:
    if _use_local_storage():
        base = current_app.config.get("LOCAL_STORAGE_BASE_URL", "/static/uploads").rstrip("/")
        if base.startswith("http://") or base.startswith("https://"):
            return base
        base = base if base.startswith("/") else f"/{base}"

        # Prefer configured base; otherwise fall back to the active request host so URLs resolve in any dev setup.
        app_base = (current_app.config.get("APP_BASE_URL") or "").rstrip("/")
        if not app_base:
            try:
                app_base = (request.host_url or "").rstrip("/")
            except RuntimeError:
                app_base = ""
        if not app_base:
            app_base = "http://localhost:5000"
        return f"{app_base}{base}"
    bucket = current_app.config.get("AWS_S3_BUCKET", "")
    region = current_app.config.get("AWS_S3_REGION", "us-east-1")
    return f"https://{bucket}.s3.{region}.amazonaws.com" if bucket else ""


def s3_public_url(key: str) -> str:
    base = _public_base_url().rstrip("/")
    return f"{base}/{key}"


def s3_public_prefix() -> str:
    base = _public_base_url().rstrip("/")
    return f"{base}/"


def get_s3_client():
    if _use_local_storage():
        return LocalS3Client(_local_storage_base_path(), _public_base_url())
    return boto3.client(
        "s3",
        region_name=current_app.config["AWS_S3_REGION"],
        aws_access_key_id=current_app.config["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=current_app.config["AWS_SECRET_ACCESS_KEY"],
    )


def upload_profile_image(user_id: str, file_storage, key: str):
    s3 = get_s3_client()
    bucket = current_app.config["AWS_S3_BUCKET"]
    try:
        s3.upload_fileobj(
            file_storage,
            bucket,
            key,
            ExtraArgs={
                "ContentType": file_storage.mimetype,
                "ACL": "public-read",
            },
        )
        return s3_public_url(key)
    except ClientError as exc:
        current_app.logger.exception("Failed to upload to S3")
        raise exc


def delete_profile_image(url: str):
    if not url:
        return
    prefix = s3_public_prefix()
    if not url.startswith(prefix):
        return
    key = url.replace(prefix, "", 1)
    s3 = get_s3_client()
    try:
        bucket = current_app.config.get("AWS_S3_BUCKET")
        s3.delete_object(Bucket=bucket, Key=key)
    except ClientError:
        current_app.logger.warning("Failed to delete old image", exc_info=True)
