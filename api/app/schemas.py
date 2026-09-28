"""
Schemas = the exact shape of data going IN to and OUT of the API.

FastAPI uses these to:
- reject bad input automatically (e.g. not an email -> 422 error)
- control output, so password_hash can never leak in a response
- draw the forms you see on /docs
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    # max 128 so nobody can send a 10 MB "password" to make hashing slow.
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until the token expires


class UserOut(BaseModel):
    """What we show about a user. Note: no password_hash field."""

    # Lets FastAPI build this straight from a SQLAlchemy User object.
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    created_at: datetime
