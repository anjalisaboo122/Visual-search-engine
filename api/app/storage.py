"""
Talking to object storage (RustFS locally, any S3-compatible store later).

Only the S3 interface is used here, so swapping RustFS for Cloudflare R2 or
AWS S3 means changing config, not code.
"""
import io
from functools import lru_cache

from minio import Minio

from api.app.config import get_settings


@lru_cache
def get_storage() -> Minio:
    settings = get_settings()
    return Minio(
        settings.s3_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        secure=settings.storage_secure,
    )


def ensure_bucket() -> None:
    """Create the bucket (a top-level folder) if it doesn't exist yet."""
    client = get_storage()
    bucket = get_settings().storage_bucket
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)


def put_bytes(key: str, data: bytes, content_type: str) -> None:
    get_storage().put_object(
        get_settings().storage_bucket,
        key,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )


def get_bytes(key: str) -> bytes:
    response = get_storage().get_object(get_settings().storage_bucket, key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def delete_object(key: str) -> None:
    get_storage().remove_object(get_settings().storage_bucket, key)
