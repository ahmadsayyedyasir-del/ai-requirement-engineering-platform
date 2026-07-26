"""
base_mixin.py — A reusable "mixin" that adds timestamp columns to any model.

WHY THIS FILE EXISTS:
  Almost every database table benefits from knowing WHEN a row was created
  and WHEN it was last updated. Rather than copy-pasting the same two columns
  into every model, we define them once here as a "mixin".

WHAT IS A MIXIN?
  A mixin is a class that is NOT meant to be used on its own. Instead, other
  classes inherit from it to gain its attributes. Think of it like a plugin.

  Example — instead of this (copy-pasted in every model):
      class User(Base):
          created_at = Column(DateTime, ...)
          updated_at = Column(DateTime, ...)

  We do this (inheriting from the mixin):
      class User(Base, TimestampMixin):
          ...  # created_at and updated_at are automatically present

HOW `server_default` vs `default` WORKS:
  `server_default=func.now()` means the DATABASE generates the timestamp
  when the row is inserted. This is more reliable than Python-side defaults
  because it uses the database server's clock (consistent across all app instances).

  `onupdate=func.now()` means the database automatically updates `updated_at`
  whenever any column in that row changes. You never have to remember to set it.
"""

# datetime is a Python type used in type hints for the timestamp columns
from datetime import datetime

# DateTime is the SQLAlchemy column type for date+time with optional timezone.
# func gives us access to SQL functions like NOW() that run on the database.
from sqlalchemy import DateTime, func

# Mapped and mapped_column are the modern SQLAlchemy 2.0 way to define columns.
# Mapped[datetime] is a type hint that tells IDEs the column holds datetime values.
# mapped_column(...) configures the actual database column properties.
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """
    Adds `created_at` and `updated_at` columns to any model that inherits this class.

    Usage:
        class MyModel(Base, TimestampMixin):
            # Your model automatically gets created_at and updated_at
            pass
    """

    # created_at: Records when the row was first inserted into the database.
    # DateTime(timezone=True) stores the time with UTC timezone info.
    # server_default=func.now() means PostgreSQL calls NOW() at insert time.
    # nullable=False means this column can never be empty/NULL.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),  # DB generates this automatically on INSERT
        nullable=False,
    )

    # updated_at: Records when the row was most recently changed.
    # server_default=func.now() sets it to NOW() on INSERT (same as created_at initially).
    # onupdate=func.now() tells SQLAlchemy to update this to NOW() on every UPDATE.
    # This means you can always look at this field to know "when was this last changed?"
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),  # Set to current time when first created
        onupdate=func.now(),        # Automatically refreshed every time the row changes
        nullable=False,
    )
