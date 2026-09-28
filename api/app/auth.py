"""
Auth endpoints:
  POST /auth/signup  -> create an account
  POST /auth/login   -> get an access token (the wristband)
  GET  /auth/me      -> protected: who am I?

Plus get_current_user, a reusable "wristband check" that any future
endpoint (upload, search...) can require with one line.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.app.config import get_settings
from api.app.db import get_db
from api.app.models import User
from api.app.schemas import LoginRequest, SignupRequest, TokenResponse, UserOut
from api.app.security import (
    InvalidToken,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# Reads the "Authorization: Bearer <token>" header. auto_error=False so that
# WE return a clean 401 when the header is missing (instead of a 403).
bearer_scheme = HTTPBearer(auto_error=False)

# A real Argon2 hash of a random password. Used when the email doesn't exist,
# so a login for a missing user takes as long as one with a wrong password.
# Otherwise an attacker could time responses to learn which emails are registered.
_DUMMY_HASH = hash_password("dummy-password-for-timing")


def _normalize_email(email: str) -> str:
    # "Anjali@X.com" and "anjali@x.com" should be the same account.
    return email.strip().lower()


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, db: Session = Depends(get_db)) -> User:
    email = _normalize_email(body.email)

    if db.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(email=email, password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Two signups with the same email at the same instant can both pass
        # the check above. The UNIQUE index in Postgres stops the second one.
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    db.refresh(user)  # load created_at, which Postgres filled in
    return user


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    email = _normalize_email(body.email)
    user = db.scalar(select(User).where(User.email == email))

    if user is None:
        verify_password(body.password, _DUMMY_HASH)  # same work, same timing
        password_ok = False
    else:
        password_ok = verify_password(body.password, user.password_hash)

    if not password_ok:
        # Same message for "no such email" and "wrong password" on purpose:
        # don't tell attackers which emails exist.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = get_settings()
    return TokenResponse(
        access_token=create_access_token(user.id),
        expires_in=settings.access_token_expire_minutes * 60,
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    The wristband check. Any endpoint that adds
        user: User = Depends(get_current_user)
    becomes protected: no valid token -> 401, and the endpoint never runs.
    """
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized

    try:
        user_id = decode_access_token(credentials.credentials)
    except InvalidToken:
        raise unauthorized

    # The token could be valid for a user who was deleted since.
    user = db.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
