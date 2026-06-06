"""SQLAlchemy declarative base and shared metadata."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """ORM base class for all PostgreSQL models."""

    pass
