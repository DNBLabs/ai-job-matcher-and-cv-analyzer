"""SQLAlchemy ORM models for application and infrastructure tables."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base
from app.domain.analysis_run import AnalysisRunStatus
from app.domain.divergence import InterviewLikelihood


class UserAccount(Base):
    """Persistent Job Seeker or Admin identity."""

    __tablename__ = "user_account"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_unlimited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    cvs: Mapped[list["Cv"]] = relationship(back_populates="user")
    analysis_runs: Mapped[list["AnalysisRun"]] = relationship(back_populates="user")


class Cv(Base):
    """Uploaded CV PDF metadata owned by a User Account."""

    __tablename__ = "cv"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("user_account.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    blob_key: Mapped[str] = mapped_column(String(512), nullable=False)
    parsed_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[UserAccount] = relationship(back_populates="cvs")
    analysis_runs: Mapped[list["AnalysisRun"]] = relationship(back_populates="cv")


class AnalysisRun(Base):
    """Single end-to-end pipeline execution for one CV and Job Search."""

    __tablename__ = "analysis_run"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("user_account.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cv_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("cv.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[AnalysisRunStatus] = mapped_column(
        SAEnum(AnalysisRunStatus, name="analysis_run_status", native_enum=False),
        nullable=False,
        default=AnalysisRunStatus.QUEUED,
    )
    job_search_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_failures_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    finops_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[UserAccount] = relationship(back_populates="analysis_runs")
    cv: Mapped[Cv] = relationship(back_populates="analysis_runs")
    job_match_results: Mapped[list["JobMatchResult"]] = relationship(back_populates="analysis_run")


class JobMatchResult(Base):
    """One scored listing within an Analysis Run."""

    __tablename__ = "job_match_result"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("analysis_run.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    company: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    match_score: Mapped[int] = mapped_column(Integer, nullable=False)
    interview_likelihood: Mapped[InterviewLikelihood] = mapped_column(
        SAEnum(InterviewLikelihood, name="interview_likelihood", native_enum=False),
        nullable=False,
    )
    breakdown_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    analysis_run: Mapped[AnalysisRun] = relationship(back_populates="job_match_results")

    __table_args__ = (
        UniqueConstraint("analysis_run_id", "source", "external_id", name="uq_job_match_result_run_source_external"),
        CheckConstraint("match_score >= 0 AND match_score <= 100", name="ck_job_match_result_match_score_range"),
    )


class MagicLinkToken(Base):
    """Hashed magic-link token for passwordless sign-in."""

    __tablename__ = "magic_link_token"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SessionRecord(Base):
    """Server-side session row backing HttpOnly session cookies."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("user_account.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RateLimitCounter(Base):
    """Rolling-window counter for auth and API rate limits."""

    __tablename__ = "rate_limit_counters"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bucket_key: Mapped[str] = mapped_column(String(512), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("bucket_key", "window_start", name="uq_rate_limit_bucket_window"),
        Index("ix_rate_limit_bucket_key", "bucket_key"),
        CheckConstraint("request_count >= 0", name="ck_rate_limit_counters_non_negative"),
    )


class AuditLogEntry(Base):
    """Append-only audit trail for auth and admin actions."""

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("user_account.id", ondelete="SET NULL"),
        nullable=True,
    )
    subject_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("user_account.id", ondelete="SET NULL"),
        nullable=True,
    )
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
