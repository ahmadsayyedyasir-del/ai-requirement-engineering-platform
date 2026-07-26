"""
schemas/auth.py — Pydantic schemas for authentication requests and responses.

WHAT ARE PYDANTIC SCHEMAS?
  Schemas define the SHAPE of data coming in (request body) and going out
  (response body). They are NOT database models — they don't map to tables.
  Their job is to:
    1. Validate incoming data (e.g., email must look like an email)
    2. Serialize outgoing data (e.g., exclude hashed_password from responses)
    3. Provide automatic API documentation in Swagger

  The key rule: NEVER return a schema that contains hashed_password.
  Always use UserOut, which deliberately omits the password hash.

WHY SEPARATE SCHEMAS FROM MODELS?
  A model (User) has ALL columns including sensitive ones (hashed_password).
  A schema (UserOut) shows ONLY the safe fields for the API response.
  This separation prevents accidentally leaking sensitive data.
"""

import uuid
from pydantic import BaseModel, EmailStr, Field
from app.models.user import UserRole


class RegisterRequest(BaseModel):
    """
    Request body for POST /auth/register.

    EmailStr is a special Pydantic type that validates the email format —
    "not-an-email" would be rejected with a 422 error automatically.
    Field() lets us add constraints like min/max length.
    """
    email: EmailStr         # Must be valid email format (e.g., user@example.com)
    full_name: str = Field(
        min_length=2,        # At least 2 characters (reject single-char names)
        max_length=255,      # Match the DB column length
    )
    password: str = Field(
        min_length=8,        # Enforce a minimum password strength
        max_length=128,      # Prevent absurdly long passwords (DoS protection)
    )


class TokenResponse(BaseModel):
    """
    Response body for POST /auth/login.

    Returned after successful authentication. The client stores `access_token`
    and sends it in every subsequent request as:
        Authorization: Bearer <access_token>

    token_type is always "bearer" — this is the OAuth2 standard value.
    """
    access_token: str       # The signed JWT string (e.g., "eyJhbGci...")
    token_type: str = "bearer"  # Always "bearer" — standard OAuth2 token type


class UserOut(BaseModel):
    """
    Safe user representation for API responses.

    IMPORTANT: This schema intentionally EXCLUDES hashed_password.
    Whenever we return user data from an endpoint, we use UserOut
    instead of the raw User model to prevent password hash exposure.

    model_config from_attributes=True tells Pydantic to build this schema
    from a SQLAlchemy ORM object (not just a dict). Without this, FastAPI
    can't serialize a User ORM object into this schema.
    """
    id: uuid.UUID       # The user's unique identifier
    email: str          # Login email address (safe to expose)
    full_name: str      # Display name
    role: UserRole      # admin | analyst | viewer
    is_active: bool     # Whether the account is enabled

    # from_attributes=True: allow building from SQLAlchemy ORM objects
    # (previously called orm_mode=True in Pydantic v1)
    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    """
    Request body for PATCH /users/{id}.

    All fields are optional (None = don't change that field).
    This is the "partial update" pattern — only send what you want to change.
    """
    full_name: str | None = None    # New display name, or None to keep current
    is_active: bool | None = None   # Only admins can change this (enforced in the endpoint)
