"""create images table

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-29
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"  # runs after the users table exists
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

image_status = sa.Enum("pending", "processing", "indexed", "failed", name="image_status")


def upgrade() -> None:
    op.create_table(
        "images",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("status", image_status, nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("embedding", sa.LargeBinary(), nullable=True),
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_images_owner_id", "images", ["owner_id"])
    op.create_index("ix_images_status", "images", ["status"])


def downgrade() -> None:
    op.drop_index("ix_images_status", table_name="images")
    op.drop_index("ix_images_owner_id", table_name="images")
    op.drop_table("images")
    image_status.drop(op.get_bind(), checkfirst=True)
