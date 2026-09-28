"""
Table definitions. Each class = one table in Postgres.
Each attribute declared with mapped_column = one column.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
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

    # Never the real password, only the Argon2 hash (added in Step 6).
    password_hash: Mapped[str] = mapped_column(String(255))

    # server_default=func.now(): Postgres fills in the time itself.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<User {self.email}>"
