"""
users.py — User management endpoints (admin-level operations).

WHY THIS FILE EXISTS:
  While auth.py handles login/register (public endpoints), this file handles
  management operations that require admin privileges:
    - List all users (so an admin can see who has accounts)
    - Get a specific user's profile
    - Update a user's name or activate/deactivate their account

  Regular users can view/edit their OWN profile.
  Admins can view/edit ANY user's profile.

  These endpoints are NOT exposed to normal analysts — they're administrative tools.
"""

# Standard library
import uuid

# FastAPI dependencies
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# Our models and schemas
from app.core.database import get_db
from app.models.user import User, UserRole
from app.schemas.auth import UserOut, UserUpdateRequest

# We reuse get_current_user from auth.py — no need to duplicate authentication logic
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    A helper dependency that raises 403 Forbidden if the user is NOT an admin.

    WHY A SEPARATE FUNCTION?
      We can reuse this across multiple endpoints:
          @router.get("/", ...)
          async def list_users(_: User = Depends(require_admin)):
      Instead of writing the same role check in every admin endpoint.

    DEPENDENCY CHAINING:
      require_admin itself depends on get_current_user.
      FastAPI resolves dependencies automatically in order:
        1. Extract token from header (oauth2_scheme)
        2. Decode token and get User (get_current_user)
        3. Check if user is admin (require_admin)
      Each step builds on the previous.
    """
    if current_user.role != UserRole.admin:
        # 403 Forbidden = "I know who you are, but you're not allowed to do this"
        # (vs 401 Unauthorized = "I don't know who you are")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


# ── LIST ALL USERS ─────────────────────────────────────────────────────────────

@router.get("/", response_model=list[UserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),   # The _ means "I need this dependency to run
                                         # (for the auth check) but I don't use its value"
):
    """
    List all user accounts. Admin only.

    Returns a list of all users sorted by registration date (newest first).
    Useful for admins managing team access.
    """
    result = await db.execute(
        select(User).order_by(User.created_at.desc())  # Newest users first
    )
    return result.scalars().all()  # .scalars() extracts User objects from the result rows


# ── GET SINGLE USER ────────────────────────────────────────────────────────────

@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: uuid.UUID,  # FastAPI automatically parses the UUID from the URL path
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get a specific user's profile by their UUID.

    Access rules:
      - Admins can get ANY user's profile
      - Regular users can only get THEIR OWN profile (current_user.id == user_id)
      - Raises 403 if a non-admin tries to access another user's profile
      - Raises 404 if the user_id doesn't exist
    """
    # Authorization check: non-admins can only see their own profile
    if current_user.role != UserRole.admin and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Fetch the requested user from the database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


# ── UPDATE USER ────────────────────────────────────────────────────────────────

@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdateRequest,  # Contains the fields to update (all optional)
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Partially update a user account. PATCH means only send the fields you want to change.

    What can be updated:
      - full_name: Anyone can change their own name. Admins can change any user's name.
      - is_active: ONLY admins can activate/deactivate accounts.
                   This is used to suspend a user without deleting them.

    WHY PATCH NOT PUT?
      PUT would require sending ALL fields (even ones you're not changing).
      PATCH is "partial update" — only send what you want to change.

    Returns the updated user object.
    """
    # Authorization: non-admins can only update their own profile
    if current_user.role != UserRole.admin and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Find the user to update
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Only update fields that were actually provided in the request.
    # `is not None` check means sending {"full_name": null} is different
    # from not sending full_name at all — Pydantic distinguishes these.
    if payload.full_name is not None:
        user.full_name = payload.full_name

    # Only admins can change account active status (suspending/reactivating users)
    if payload.is_active is not None and current_user.role == UserRole.admin:
        user.is_active = payload.is_active

    # Stage the UPDATE — get_db will commit when the request finishes
    await db.flush()

    return user
