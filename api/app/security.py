"""
The two security tools auth needs. No web or database code here.

1. Password hashing (Argon2): turn a password into a one-way scramble,
   and check a typed password against a stored scramble.
2. JWT tokens (the "wristband"): create a signed token for a user,
   and read one back, rejecting anything forged or expired.
"""
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from api.app.config import get_settings

# Argon2 with the library's recommended settings.
password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """'hunter2hunter2' -> '$argon2id$v=19$m=65536,t=3,p=4$...' (different every time)."""
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Scramble what the user typed the same way and compare. True if it matches."""
    return password_hasher.verify(password, password_hash)


def create_access_token(user_id: uuid.UUID) -> str:
    """
    Build the wristband. The payload (the "claims") says:
      sub  = who this token is for (the user's id)
      type = "access" (refresh tokens will get a different type later)
      iat  = issued at
      exp  = expires at
    jwt.encode then signs it with JWT_SECRET. Change one character of the
    token and the signature no longer matches.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


class InvalidToken(Exception):
    """Raised for any bad token: forged, expired, malformed, or wrong type."""


def decode_access_token(token: str) -> uuid.UUID:
    """Check the signature and expiry, then return the user id inside the token."""
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            # Only accept the algorithm WE use. Never trust the token's own header
            # to pick the algorithm, which is a classic JWT attack.
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp", "iat", "type"]},
        )
    except jwt.PyJWTError as exc:  # bad signature, expired, missing claims...
        raise InvalidToken(str(exc)) from exc

    if claims["type"] != "access":
        raise InvalidToken("not an access token")

    try:
        return uuid.UUID(claims["sub"])
    except ValueError as exc:
        raise InvalidToken("bad subject") from exc
