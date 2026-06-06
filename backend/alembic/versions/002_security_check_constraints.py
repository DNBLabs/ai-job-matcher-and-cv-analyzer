"""Add database-level check constraints for Task 2 security boundaries."""

from typing import Sequence, Union

from alembic import op

revision: str = "002_security_check_constraints"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Enforce Match Score and rate-limit counter bounds at the database layer."""
    op.create_check_constraint(
        "ck_job_match_result_match_score_range",
        "job_match_result",
        "match_score >= 0 AND match_score <= 100",
    )
    op.create_check_constraint(
        "ck_rate_limit_counters_non_negative",
        "rate_limit_counters",
        "request_count >= 0",
    )


def downgrade() -> None:
    """Remove security check constraints."""
    op.drop_constraint("ck_rate_limit_counters_non_negative", "rate_limit_counters", type_="check")
    op.drop_constraint("ck_job_match_result_match_score_range", "job_match_result", type_="check")
