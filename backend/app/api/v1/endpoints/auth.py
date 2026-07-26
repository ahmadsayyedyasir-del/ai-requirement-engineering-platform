"""
auth.py — Authentication endpoints: register, login, and "who am I?"

WHY THIS FILE EXISTS:
  Before any other feature can work, users need to be able to:
    1. Create an account (register)
    2. Prove who they are (login → get a JWT token)
    3. Ask "who am I currently logged in as?" (me)

HOW JWT AUTHENTICATION WORKS (big picture):
  Step 1 — Registration: User provides email + password.
            We hash the password with bcrypt and store the hash.
            We NEVER store the plain password.

  Step 2 — Login: User sends email + password.
            We look up the user, verify the password against the stored hash.
            If correct, we issue a JWT token (a signed string).
            The token contains the user's ID and role.

  Step 3 — Every subsequent request: The browser/client sends the JWT token
            in the Authorization header: "Authorization: Bearer <token>"
            The `get_current_user` dependency decodes and verifies the token.
            If valid, the endpoint receives the authenticated User object.

WHY OAUTH2PasswordRequestForm?
  OAuth2 is an authentication standard. FastAPI supports it out of the box.
  The login form expects `username` and `password` fields (not `email`).
  We use email as the username — the form doesn't care about the field name.
  This also makes Swagger's "Authorize" button work automatically.
"""

# Standard library
import uuid

# FastAPI tools:
# APIRouter — groups these endpoints together
# Depends — declares a dependency (called automatically before the endpoint)
# HTTPException — raises an HTTP error response (e.g., 401 Unauthorized)
# status — constants for HTTP status codes (status.HTTP_201_CREATED = 201)
from fastapi import APIRouter, Depends, HTTPException, status

# OAuth2PasswordRequestForm — parses the standard login form (username + password)
# OAuth2PasswordBearer — tells FastAPI "look for a Bearer token in Authorization header"
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer

# AsyncSession — the async database session type
from sqlalchemy.ext.asyncio import AsyncSession

# select — builds a SQL SELECT query in Python
from sqlalchemy import select

# Import our database dependency (gives us a DB session per request)
from app.core.database import get_db

# Security utilities for hashing, verifying, and creating tokens
from app.core.security import hash_password, verify_password, create_access_token, decode_access_token

# The User ORM model and its role enum
from app.models.user import User, UserRole

# Pydantic schemas — define the shape of request/response JSON
from app.schemas.auth import TokenResponse, RegisterRequest, UserOut

# Create the router for this module
router = APIRouter()

# OAuth2 scheme — tells FastAPI where to find the token in each request.
# tokenUrl="/api/v1/auth/login" points Swagger's Authorize button to our login URL.
# When a request comes in, FastAPI automatically extracts the token from
# "Authorization: Bearer <token>" and passes it to dependencies that use this scheme.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),  # FastAPI auto-extracts the Bearer token
    db: AsyncSession = Depends(get_db),   # We need the DB to look up the user
) -> User:
    """
    A SHARED DEPENDENCY used by every protected endpoint.

    Instead of writing authentication logic in every single endpoint, we write
    it once here and inject it via `Depends(get_current_user)`.

    HOW IT WORKS:
      1. FastAPI extracts the JWT token from the Authorization header
      2. We decode it to get the user's ID (stored in the "sub" claim)
      3. We look up the user in the database
      4. We return the User object — the endpoint receives it directly

    If anything goes wrong (bad token, expired token, user not found),
    we raise HTTP 401 — the browser knows to redirect to the login page.

    WHY RAISE `credentials_exc` IN TWO PLACES?
      We always raise the SAME generic error regardless of what went wrong.
      If we said "user not found" vs "token expired", attackers could use
      the different errors to probe our system. Generic = safer.
    """
    # Prepare a reusable 401 error. We raise this for ANY auth failure.
    # WWW-Authenticate header is part of the HTTP spec for 401 responses.
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Decode the JWT. This raises an exception if:
        #   - The token was tampered with (signature invalid)
        #   - The token has expired
        #   - The token is malformed
        payload = decode_access_token(token)

        # "sub" is the JWT standard claim for "subject" (who this token is about).
        # We stored the user's UUID string here during login.
        user_id: str = payload.get("sub")
        if user_id is None:
            # Token exists but doesn't contain a user ID — something is wrong
            raise credentials_exc
    except Exception:
        # Catch all JWT decode errors (expired, invalid, etc.)
        raise credentials_exc

    # Look up the user by their UUID in the database
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()  # Returns None if not found

    # Reject if the user doesn't exist or their account has been deactivated
    if user is None or not user.is_active:
        raise credentials_exc

    return user  # The endpoint will receive this User object


# ── REGISTER ENDPOINT ──────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=UserOut,       # The response will be shaped like UserOut (hides password hash)
    status_code=status.HTTP_201_CREATED,  # 201 = "Created" (not 200 = "OK")
)
async def register(
    payload: RegisterRequest,         # The request body (email, full_name, password)
    db: AsyncSession = Depends(get_db),  # Injected DB session
):
    """
    Create a new analyst account.

    Checks if the email is already registered, then creates a new User row
    with the password hashed using bcrypt.

    Returns the created user's details (without the password hash).
    Raises 400 if the email is already taken.
    """
    # Check if a user with this email already exists
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        # 400 Bad Request — the client sent invalid data (duplicate email)
        raise HTTPException(status_code=400, detail="Email already registered")

    # Create the new user object.
    # hash_password() converts the plain password to a bcrypt hash BEFORE storing.
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),  # NEVER store plain password
        role=UserRole.analyst,  # Default role for new registrations
    )
    db.add(user)       # Stage the INSERT
    await db.flush()   # Execute the INSERT (but don't commit yet — get_db handles commit)

    # FastAPI automatically serializes `user` to JSON using the UserOut schema
    return user


# ── LOGIN ENDPOINT ─────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(
    # OAuth2PasswordRequestForm parses a form-encoded body with `username` and `password`.
    # The `username` field is what we use for email (standard OAuth2 naming).
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate with email + password. Returns a JWT access token.

    The token should be stored by the client (localStorage in the browser)
    and sent as "Authorization: Bearer <token>" on every subsequent request.

    Raises 401 if credentials are wrong or the account is inactive.
    """
    # Look up the user by email (form_data.username holds the email)
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    # Verify the password. We use `not user` first to short-circuit:
    # no point running verify_password if the user doesn't exist.
    # SECURITY NOTE: We return the SAME error for "wrong email" and "wrong password"
    # so attackers can't enumerate which emails are registered.
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Reject suspended accounts
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Account is inactive")

    # Create a JWT token. The "sub" claim holds the user's UUID (as a string).
    # The "role" is included so endpoints can check permissions without a DB query.
    token = create_access_token({"sub": str(user.id), "role": user.role})

    # Return the token. The client must store this and send it with every request.
    return TokenResponse(access_token=token, token_type="bearer")


# ── ME ENDPOINT ────────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserOut)
async def me(
    # get_current_user is injected — it validates the token and returns the User
    current_user: User = Depends(get_current_user),
):
    """
    Return the profile of the currently authenticated user.

    The frontend calls this endpoint on app startup to check if the stored
    token is still valid and to get the user's name/role for display.
    Returns 401 automatically if the token is missing or invalid (from get_current_user).
    """
    return current_user  # Serialized to UserOut (hides hashed_password)
