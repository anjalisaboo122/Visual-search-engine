"""
Table definitions. Each class = one table in Postgres.
Each attribute declared with mapped_column = one column.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, LargeBinary, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from api.app.db import Base


class User(Base):
    __tablename__ = "users"

    # UUID instead of 1, 2, 3...: can't be guessed, and safe to create
    # on any machine without asking the database for the next number.
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # unique=True: two users can't share an email.
    # index=True: login looks users up by email, so make that lookup fast.
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)

    # Never the real password, only the Argon2 hash.
    password_hash: Mapped[str] = mapped_column(String(255))

    # server_default=func.now(): Postgres fills in the time itself.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<User {self.email}>"


class ImageStatus(str, enum.Enum):
    """
    The life of an image:
      pending    -> uploaded, waiting in the queue
      processing -> a worker is computing its embedding
      indexed    -> embedding saved, image is searchable
      failed     -> gave up after too many attempts (see `error`)
    """

    pending = "pending"
    processing = "processing"
    indexed = "indexed"
    failed = "failed"


class Image(Base):
    __tablename__ = "images"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # ondelete=CASCADE: delete a user -> their image rows go too.
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    # Where the file lives in object storage, e.g. "originals/<id>.jpg".
    storage_key: Mapped[str] = mapped_column(String(512))
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)

    status: Mapped[ImageStatus] = mapped_column(
        Enum(ImageStatus, name="image_status"),
        default=ImageStatus.pending,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)

    # The 512 CLIP numbers, stored as raw float32 bytes (512 x 4 = 2048 bytes).
    # Postgres is the source of truth; the FAISS index (Phase 3) is built from this,
    # so a lost index can always be rebuilt.
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)
    embedding_model: Mapped[str | None] = mapped_column(String(128))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<Image {self.id} {self.status.value}>"
