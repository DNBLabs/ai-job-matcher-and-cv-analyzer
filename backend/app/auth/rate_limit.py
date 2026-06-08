"""Postgres-backed rolling-window rate limit counters for auth endpoints."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.db.models import RateLimitCounter

MAGIC_LINK_EMAIL_LIMIT = 3
MAGIC_LINK_IP_LIMIT = 10
MAGIC_LINK_RATE_WINDOW = timedelta(hours=1)


class RateLimitExceeded(Exception):
    """Raised when a rate-limit bucket would exceed its configured threshold."""


def magic_link_email_bucket(email: str) -> str:
    """Return the rate-limit bucket key for magic-link requests by email.

    Args:
        email: Normalized recipient email address.

    Returns:
        str: Stable bucket identifier for per-email counters.
    """
    return f"magic_link:email:{email}"


def magic_link_ip_bucket(client_ip: str) -> str:
    """Return the rate-limit bucket key for magic-link requests by client IP.

    Args:
        client_ip: Observed client IP address from the incoming request.

    Returns:
        str: Stable bucket identifier for per-IP counters.
    """
    return f"magic_link:ip:{client_ip}"


def floor_to_window_start(value: datetime, window: timedelta) -> datetime:
    """Align a timestamp to the start of its fixed-width window.

    Args:
        value: Current instant used for counter lookup.
        window: Rolling window duration (one hour for magic-link limits).

    Returns:
        datetime: Naive UTC window boundary stored in ``rate_limit_counters``.
    """
    aware_value = value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    epoch_seconds = int(aware_value.timestamp())
    window_seconds = int(window.total_seconds())
    aligned_epoch = epoch_seconds - (epoch_seconds % window_seconds)
    return datetime.fromtimestamp(aligned_epoch, tz=UTC).replace(tzinfo=None)


class RateLimiter:
    """Increment and evaluate rolling-window counters stored in PostgreSQL."""

    def __init__(self, db: Session) -> None:
        """Bind the limiter to an active SQLAlchemy session.

        Args:
            db: Unit-of-work session for database operations.
        """
        self._db = db

    def check_and_increment(
        self,
        *,
        bucket_key: str,
        limit: int,
        window: timedelta = MAGIC_LINK_RATE_WINDOW,
        now: datetime | None = None,
    ) -> None:
        """Increment a bucket and raise when the configured limit is exceeded.

        Args:
            bucket_key: Stable identifier for the actor being limited.
            limit: Maximum allowed requests within the window.
            window: Rolling window duration.
            now: Optional clock override for deterministic tests.

        Raises:
            RateLimitExceeded: When the incremented count exceeds ``limit``.
        """
        current_time = now.astimezone(UTC) if now and now.tzinfo else (now or datetime.now(UTC))
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=UTC)

        window_start = floor_to_window_start(current_time, window)
        new_count = self._increment_counter(bucket_key=bucket_key, window_start=window_start)
        if new_count > limit:
            raise RateLimitExceeded(bucket_key)

    def _increment_counter(self, *, bucket_key: str, window_start: datetime) -> int:
        """Atomically increment a counter row and return the updated count.

        Args:
            bucket_key: Stable identifier for the actor being limited.
            window_start: Aligned window boundary for the counter row.

        Returns:
            int: Updated request count after increment.
        """
        dialect_name = self._db.get_bind().dialect.name
        insert_builder = pg_insert if dialect_name == "postgresql" else sqlite_insert
        statement = insert_builder(RateLimitCounter).values(
            bucket_key=bucket_key,
            window_start=window_start,
            request_count=1,
        )
        statement = statement.on_conflict_do_update(
            index_elements=["bucket_key", "window_start"],
            set_={"request_count": RateLimitCounter.request_count + 1},
        )
        self._db.execute(statement)
        self._db.flush()

        updated_count = self._db.scalar(
            select(RateLimitCounter.request_count).where(
                RateLimitCounter.bucket_key == bucket_key,
                RateLimitCounter.window_start == window_start,
            )
        )
        self._db.commit()
        return updated_count or 0
