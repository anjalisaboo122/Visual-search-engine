"""
Image endpoints (all require login):
  POST /images            -> upload an image; returns immediately (202)
  GET  /images            -> list my images and their status
  GET  /images/{id}       -> one image's status
  GET  /images/{id}/file  -> the image file itself

The upload does NOT compute the embedding. It stores the file, writes a
"pending" row, drops a ticket on the queue, and returns. The worker does
the slow CLIP work in the background.
"""
import io
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from PIL import Image as PILImage
from PIL import UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.app import jobs, storage
from api.app.auth import get_current_user
from api.app.config import get_settings
from api.app.db import get_db
from api.app.models import Image, User
from api.app.schemas import ImageOut

log = logging.getLogger(__name__)

router = APIRouter(prefix="/images", tags=["images"])

# What Pillow calls each format -> (content type, file extension).
# We trust the actual file contents, not the filename or what the browser claims.
ALLOWED_FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}

# Refuse "decompression bombs": tiny files that expand to gigantic images.
PILImage.MAX_IMAGE_PIXELS = 50_000_000


def _inspect_image(data: bytes) -> tuple[str, str, int, int]:
    """Check the bytes really are an allowed image. Returns (content_type, ext, width, height)."""
    try:
        with PILImage.open(io.BytesIO(data)) as img:
            img.verify()  # checks the file structure without decoding every pixel
            fmt = img.format
            width, height = img.size
    except (UnidentifiedImageError, OSError, SyntaxError, PILImage.DecompressionBombError):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Not a valid image file")

    if fmt not in ALLOWED_FORMATS:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only JPEG, PNG and WebP are allowed"
        )
    content_type, ext = ALLOWED_FORMATS[fmt]
    return content_type, ext, width, height


@router.post("", response_model=ImageOut, status_code=status.HTTP_202_ACCEPTED)
def upload_image(
    file: UploadFile,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Image:
    settings = get_settings()
    max_bytes = settings.max_upload_mb * 1024 * 1024

    # Read one byte more than allowed, so we can tell "too big" without reading everything.
    data = file.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"File larger than {settings.max_upload_mb} MB",
        )
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file")

    content_type, ext, width, height = _inspect_image(data)

    image_id = uuid.uuid4()
    key = f"originals/{image_id}.{ext}"

    # 1. File -> storage
    storage.put_bytes(key, data, content_type)

    # 2. Row -> Postgres (status "pending")
    image = Image(
        id=image_id,
        owner_id=user.id,
        storage_key=key,
        original_filename=(file.filename or "upload")[:255],
        content_type=content_type,
        size_bytes=len(data),
        width=width,
        height=height,
    )
    db.add(image)
    try:
        db.commit()
    except Exception:
        db.rollback()
        storage.delete_object(key)  # don't leave an orphan file behind
        raise
    db.refresh(image)

    # 3. Ticket -> queue.
    # Row first, ticket second: otherwise a fast worker could pick up the ticket
    # before the row exists. If this step fails, the row stays "pending" and the
    # worker's sweep (worker/worker.py) re-queues it, so the image isn't lost.
    try:
        jobs.enqueue_embedding_job(image.id)
    except Exception:
        log.exception("Could not enqueue image %s; the worker sweep will retry it", image.id)

    return image


@router.get("", response_model=list[ImageOut])
def list_my_images(
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Image]:
    limit = max(1, min(limit, 200))
    return list(
        db.scalars(
            select(Image)
            .where(Image.owner_id == user.id)
            .order_by(Image.created_at.desc())
            .limit(limit)
        )
    )


def _get_own_image(image_id: uuid.UUID, user: User, db: Session) -> Image:
    image = db.get(Image, image_id)
    # Someone else's image looks exactly like a missing one: 404, not 403,
    # so ids of other people's images can't be probed.
    if image is None or image.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")
    return image


@router.get("/{image_id}", response_model=ImageOut)
def get_image(
    image_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Image:
    return _get_own_image(image_id, user, db)


@router.get("/{image_id}/file")
def get_image_file(
    image_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    image = _get_own_image(image_id, user, db)
    return Response(content=storage.get_bytes(image.storage_key), media_type=image.content_type)
