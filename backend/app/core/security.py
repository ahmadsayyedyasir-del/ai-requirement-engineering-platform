"""
security.py — Authentication and authorization utilities.

WHY THIS FILE EXISTS:
  User passwords must NEVER be stored as plain text in the database.
  If the database is ever breached, plain-text passwords expose every user.
  Instead, we "hash" passwords — transform them into a one-way scrambled string.
  You can verify a password by hashing the input and comparing to the stored hash,
  but you cannot reverse a hash back to the original password.

  We also use JWTs (JSON Web Tokens) for stateless authentication:
  - On login, the server creates a signed token containing the user's ID.
  - The browser stores this token and sends it with every request.
  - The server verifies the token's signature to authenticate the user.
  - No session storage is needed — the token itself proves identity.

KEY CONCEPTS:
  bcrypt: A password hashing algorithm designed to be slow (making brute-force
          attacks impractical). The "cost factor" is built in.

  JWT:    A URL-safe token format: header.payload.signature
          The header says which algorithm was used.
          The payload contains claims (user_id, expiry time).
          The signature proves the payload wasn't tampered with.
"""

# timedelta lets us express "expires in 24 hours" as a Python object.
# datetime and timezone let us work with aware datetimes (UTC).
from datetime import datetime, timedelta, timezone

# Optional is a type hint meaning "this value might be None".
from typing import Optional

# PyJWT is the library we use to create and verify JWT tokens.
import jwt

# CryptContext manages password hashing. It supports multiple algorithms
# and handles algorithm upgrades (e.g., migrating from SHA to bcrypt).
from passlib.context import CryptContext

# Import settings to get the SECRET_KEY used for signing tokens.
from app.core.config import settings

# --- Password Hashing Setup ---
# Create a CryptContext that uses bcrypt as the hashing algorithm.
# bcrypt is the industry standard — it's slow by design to resist brute force,
# and it automatically salts passwords (adds random data to prevent rainbow tables).
# deprecated="auto" means old hashes are automatically re-hashed on next login.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# The signing algorithm for JWTs. HS256 = HMAC with SHA-256.
# This is a symmetric algorithm — the same secret key is used to sign and verify.
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """
    Convert a plain-text password into a bcrypt hash for safe storage.

    WHY: Storing plain passwords is dangerous. Even if the DB is leaked,
    attackers can't reverse a bcrypt hash to get the original password.

    Example:
        hash_password("mypassword123")
        → "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36ZDl.q8hxq0"
    """
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """
    Check if a plain-text password matches a stored bcrypt hash.

    WHY: When a user logs in, we can't decrypt their stored hash.
    Instead, we hash what they typed and check if the result matches.

    Returns True if the password is correct, False otherwise.

    Example:
        verify_password("mypassword123", stored_hash) → True
        verify_password("wrongpassword", stored_hash) → False
    """
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a signed JWT access token containing the given data.

    WHY: After successful login, we give the user a token they can store
    in the browser. They include this token in every future request so we
    know who they are without them logging in again.

    Args:
        data: The payload to encode (usually {"sub": user_id, "role": "analyst"}).
              "sub" is a JWT standard claim meaning "subject" (who this token is about).
        expires_delta: How long until this token expires. Uses the config default if None.

    Returns:
        A JWT string like "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyMTIzIn0.abc"
    """
    # Make a copy so we don't modify the original dict
    to_encode = data.copy()

    # Calculate the expiry timestamp. We use UTC to avoid timezone confusion.
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    # Add the expiry claim to the payload. The "exp" key is a JWT standard.
    to_encode.update({"exp": expire})

    # Sign and encode the token using our secret key.
    # The secret key ensures no one can forge a valid token without it.
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Decode and verify a JWT token, returning the payload dict.

    WHY: Every protected endpoint calls this to extract the user's ID
    from the token they sent in the Authorization header.

    This function raises an exception if:
      - The token was tampered with (signature mismatch)
      - The token has expired ("exp" claim is in the past)
      - The token is malformed (not valid JWT format)

    Args:
        token: The JWT string from the Authorization header.

    Returns:
        The decoded payload dict, e.g., {"sub": "user-uuid", "role": "analyst"}
    """
    # jwt.decode verifies the signature and expiry automatically.
    # It raises jwt.ExpiredSignatureError or jwt.InvalidTokenError on failure.
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
