"""Bootstrap script to seed the operator Admin User account (Task 2 stub).

Usage:
    ADMIN_EMAIL=you@example.com python -m scripts.seed_admin

Full upsert logic is implemented in Task 24; this stub validates wiring only.
"""

from __future__ import annotations

import os
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import UserAccount
from app.db.session import get_session_factory
from app.domain.validation import normalize_email


def seed_admin(*, email: str, session: Session) -> UserAccount:
    """Ensure an admin User Account exists for the operator email.

    Args:
        email: Operator email to bootstrap with is_admin and is_unlimited.
        session: Active SQLAlchemy session.

    Returns:
        UserAccount: Existing or newly created admin row.

    Raises:
        ValueError: When the email fails boundary validation.
    """
    normalized = normalize_email(email)

    existing = session.scalar(select(UserAccount).where(UserAccount.email == normalized))
    if existing is not None:
        existing.is_admin = True
        existing.is_unlimited = True
        session.commit()
        session.refresh(existing)
        return existing

    admin = UserAccount(email=normalized, is_admin=True, is_unlimited=True)
    session.add(admin)
    session.commit()
    session.refresh(admin)
    return admin


def main() -> int:
    """Entry point for CLI admin bootstrap."""
    email = os.environ.get("ADMIN_EMAIL")
    if not email:
        print("Set ADMIN_EMAIL to seed the operator admin account.", file=sys.stderr)
        return 1

    session_factory = get_session_factory()
    with session_factory() as session:
        admin = seed_admin(email=email, session=session)
        print(f"Admin user ready: {admin.email} (id={admin.id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
