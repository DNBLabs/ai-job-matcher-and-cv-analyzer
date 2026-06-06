"""Initial PostgreSQL schema for Task 2 domain tables."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create application and infrastructure tables."""
    op.create_table(
        "user_account",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("google_sub", sa.String(length=255), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_unlimited", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("email", name="uq_user_account_email"),
        sa.UniqueConstraint("google_sub", name="uq_user_account_google_sub"),
    )
    op.create_index("ix_user_account_email", "user_account", ["email"], unique=False)

    op.create_table(
        "cv",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("blob_key", sa.String(length=512), nullable=False),
        sa.Column("parsed_text", sa.Text(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_cv_user_id", "cv", ["user_id"], unique=False)

    op.create_table(
        "analysis_run",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cv_id", sa.Uuid(as_uuid=True), sa.ForeignKey("cv.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("job_search_json", sa.JSON(), nullable=False),
        sa.Column("source_failures_json", sa.JSON(), nullable=True),
        sa.Column("finops_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_analysis_run_user_id", "analysis_run", ["user_id"], unique=False)
    op.create_index("ix_analysis_run_cv_id", "analysis_run", ["cv_id"], unique=False)

    op.create_table(
        "job_match_result",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "analysis_run_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("analysis_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("company", sa.String(length=500), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("match_score", sa.Integer(), nullable=False),
        sa.Column("interview_likelihood", sa.String(length=16), nullable=False),
        sa.Column("breakdown_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint(
            "analysis_run_id",
            "source",
            "external_id",
            name="uq_job_match_result_run_source_external",
        ),
    )
    op.create_index("ix_job_match_result_analysis_run_id", "job_match_result", ["analysis_run_id"], unique=False)

    op.create_table(
        "magic_link_token",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_magic_link_token_hash"),
    )
    op.create_index("ix_magic_link_token_email", "magic_link_token", ["email"], unique=False)

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=128), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], unique=False)

    op.create_table(
        "rate_limit_counters",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("bucket_key", sa.String(length=512), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint("bucket_key", "window_start", name="uq_rate_limit_bucket_window"),
    )
    op.create_index("ix_rate_limit_bucket_key", "rate_limit_counters", ["bucket_key"], unique=False)

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True),
        sa.Column("subject_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_audit_log_event_type", "audit_log", ["event_type"], unique=False)


def downgrade() -> None:
    """Drop application and infrastructure tables."""
    op.drop_index("ix_audit_log_event_type", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("ix_rate_limit_bucket_key", table_name="rate_limit_counters")
    op.drop_table("rate_limit_counters")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_magic_link_token_email", table_name="magic_link_token")
    op.drop_table("magic_link_token")
    op.drop_index("ix_job_match_result_analysis_run_id", table_name="job_match_result")
    op.drop_table("job_match_result")
    op.drop_index("ix_analysis_run_cv_id", table_name="analysis_run")
    op.drop_index("ix_analysis_run_user_id", table_name="analysis_run")
    op.drop_table("analysis_run")
    op.drop_index("ix_cv_user_id", table_name="cv")
    op.drop_table("cv")
    op.drop_index("ix_user_account_email", table_name="user_account")
    op.drop_table("user_account")
