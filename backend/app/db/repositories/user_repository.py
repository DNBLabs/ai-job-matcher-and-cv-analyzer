"""Operator-facing persistence queries for User Account records."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import UserAccount

# Cap admin search results so a broad query cannot dump the whole table.
ADMIN_SEARCH_LIMIT = 50


def _escape_like(term: str) -> str:
    """Escape LIKE wildcards so user input is matched literally.

    Args:
        term: Raw search fragment from the operator.

    Returns:
        str: Term with ``\\``, ``%``, and ``_`` escaped for an ESCAPE '\\' clause.
    """
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class UserRepository:
    """Load and update User Account rows for the admin operator console."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to an active SQLAlchemy session.

        Args:
            session: Unit-of-work session for database operations.
        """
        self._session = session

    def get_by_id(self, user_id: uuid.UUID) -> UserAccount | None:
        """Return a User Account by primary key, or None when absent.

        Args:
            user_id: User Account primary key.

        Returns:
            UserAccount | None: Matching row or None.
        """
        return self._session.get(UserAccount, user_id)

    def search_by_email(self, query: str, *, limit: int = ADMIN_SEARCH_LIMIT) -> list[UserAccount]:
        """Return accounts whose email contains the query, case-insensitively.

        Args:
            query: Email fragment to match; LIKE wildcards are escaped.
            limit: Maximum rows returned to bound result size.

        Returns:
            list[UserAccount]: Matching rows ordered by email, empty for a blank query.
        """
        normalized = query.strip().lower()
        if not normalized:
            return []

        pattern = f"%{_escape_like(normalized)}%"
        statement = (
            select(UserAccount)
            .where(UserAccount.email.ilike(pattern, escape="\\"))
            .order_by(UserAccount.email)
            .limit(limit)
        )
        return list(self._session.scalars(statement))

    def set_unlimited(self, user_id: uuid.UUID, *, is_unlimited: bool) -> UserAccount | None:
        """Update the ``is_unlimited`` flag for an account.

        Args:
            user_id: User Account primary key.
            is_unlimited: New unlimited-quota state.

        Returns:
            UserAccount | None: Updated row, or None when the account does not exist.
        """
        user = self._session.get(UserAccount, user_id)
        if user is None:
            return None

        user.is_unlimited = is_unlimited
        self._session.commit()
        self._session.refresh(user)
        return user
