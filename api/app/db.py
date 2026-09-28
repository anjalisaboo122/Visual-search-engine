"""
Database connection setup.

- engine:       the long-lived connection pool to Postgres (created once).
- SessionLocal: a factory that hands out short-lived "sessions" (one per request).
- Base:         the parent class every table model inherits from.
- get_db:       a FastAPI dependency that opens a session for a request
                and always closes it afterwards.
"""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from api.app.config import get_settings

settings = get_settings()

# pool_pre_ping=True: before reusing a pooled connection, check it's still alive.
# Avoids errors if Postgres restarted while the API was running.
engine = create_engine(settings.database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """All models (User, Image, ...) inherit from this."""


def get_db() -> Generator[Session, None, None]:
    """
    Usage in an endpoint:
        def signup(db: Session = Depends(get_db)): ...
    FastAPI calls this, gives the endpoint the session, and runs the
    `finally` block after the response is sent.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
