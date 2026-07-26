"""
user.py — The User database model (maps to the `users` table in PostgreSQL).

WHY THIS FILE EXISTS:
  The platform supports multiple analysts working on different projects.
  This model stores their login credentials and access roles.

WHAT IS AN ORM MODEL?
  ORM = Object-Relational Mapper. Instead of writing SQL like:
      INSERT INTO users (email, name) VALUES ('a@b.com', 'Alice');
  We work with Python objects:
      user = User(email='a@b.com', full_name='Alice')
      db.add(user)
  SQLAlchemy translates these operations to SQL automatically.

TABLE STRUCTURE (what the `users` table looks like in the DB):
  id              UUID        Primary key, auto-generated
  email           VARCHAR     Unique login identifier (indexed for fast lookup)
  full_name       VARCHAR     Display name
  hashed_password VARCHAR     bcrypt hash — NEVER the plain password
  role            ENUM        admin | analyst | viewer
  is_active       BOOLEAN     False = soft-deleted / suspended account
  created_at      TIMESTAMP   From TimestampMixin
  updated_at      TIMESTAMP   From TimestampMixin

RELATIONSHIPS:
  A User can own many Projects (one-to-many).
  If a User is deleted, all their Projects are deleted too (CASCADE).
"""

# uuid is Python's standard library for generating UUID (Universally Unique IDs).
# We use UUIDs instead of auto-increment integers because:
#   - They are globally unique (safe to generate without a DB round-trip)
#   - They don't expose how many records exist (security benefit)
import uuid

# SQLAlchemy column types and decorators
from sqlalchemy import String, Boolean, Enum as SAEnum

# Mapped and mapped_column for type-safe column definitions (SQLAlchemy 2.0 style)
# relationship defines how models relate to each other (foreign key joins)
from sqlalchemy.orm import Mapped, mapped_column, relationship

# UUID column type specific to PostgreSQL
# as_uuid=True means SQLAlchemy returns Python uuid.UUID objects (not strings)
from sqlalchemy.dialects.postgresql import UUID

# Python's enum module for defining a fixed set of valid values
import enum

# Base is the parent class all models must inherit from
from app.core.database import Base

# TimestampMixin adds created_at and updated_at automatically
from app.models.base_mixin import TimestampMixin


class UserRole(str, enum.Enum):
    """
    Defines the three permission levels in the system.

    WHY USE AN ENUM?
      Restricting roles to a fixed set prevents typos like "Analyst" vs "analyst"
      and makes it easy to check permissions: if user.role == UserRole.admin

    admin   — full access: can manage users, see all projects, change any setting
    analyst — standard user: can create projects and run the AI pipeline
    viewer  — read-only: can view results but cannot trigger analysis or editing
    """
    admin = "admin"
    analyst = "analyst"
    viewer = "viewer"


class User(Base, TimestampMixin):
    """
    SQLAlchemy ORM model for the `users` table.

    Inheriting from Base registers this class with SQLAlchemy's table registry.
    Inheriting from TimestampMixin adds created_at and updated_at columns.
    """

    # __tablename__ tells SQLAlchemy what to name the table in PostgreSQL.
    # Convention: lowercase, plural, snake_case.
    __tablename__ = "users"

    # Primary Key — every row needs a unique identifier.
    # UUID(as_uuid=True) stores as a native PostgreSQL UUID type (efficient).
    # default=uuid.uuid4 means Python generates a new UUID when creating a User object.
    # We use uuid.uuid4 (the function itself, not uuid.uuid4()) so it's called
    # fresh each time — not a single shared UUID for all users.
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Email — used as the login username.
    # unique=True creates a UNIQUE constraint in the DB (can't have two accounts with same email).
    # index=True creates a B-tree index for fast lookups by email (used in login queries).
    # nullable=False means this field is required.
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )

    # Full name — displayed in the UI and on documents.
    # String(255) = up to 255 characters (standard for names).
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Hashed password — the bcrypt hash of the user's password.
    # IMPORTANT: We NEVER store the plain password. Only the hash goes here.
    # String(255) is enough because bcrypt hashes are always ~60 chars.
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    # Role — determines what the user can do.
    # SAEnum(UserRole) maps the Python enum to a PostgreSQL ENUM type.
    # default=UserRole.analyst means new accounts are analysts unless explicitly set.
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole), default=UserRole.analyst, nullable=False
    )

    # is_active — allows soft-deletion and account suspension.
    # Instead of deleting a user (which could break foreign keys), we set this to False.
    # All authentication checks verify is_active=True before allowing login.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # --- RELATIONSHIP ---
    # This tells SQLAlchemy: "A User has many Projects. Access them via user.projects"
    # back_populates="owner" means the Project model has a matching .owner attribute.
    # cascade="all, delete-orphan" means if this User is deleted, all their Projects
    # are automatically deleted too (no orphaned projects without an owner).
    projects: Mapped[list["Project"]] = relationship(  # noqa: F821
        "Project", back_populates="owner", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """
        A developer-friendly string representation for debugging.
        Shown when you print a User object in a Python shell or log.
        """
        return f"<User {self.email} [{self.role}]>"
