"""Unit tests for TitleSuggestionService with a fake LLM client."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLogEntry, Cv, UserAccount
from app.domain.title_suggestion import SuggestedTitle, TitleSuggestionsLlmOutput
from app.ports.llm_client import LlmClientError
from app.services.title_suggestion_service import (
    CvTextUnavailableError,
    TitleSuggestionResponseError,
    TitleSuggestionService,
)
from tests.auth.conftest import create_test_user
from tests.fakes.fake_llm_client import FakeLlmClient


def _seed_cv(db_session: Session, user: UserAccount, *, parsed_text: str | None) -> Cv:
    """Persist a CV row with optional parsed text for service-level tests."""
    cv = Cv(
        id=uuid.uuid4(),
        user_id=user.id,
        name="Engineer CV",
        blob_key=f"cvs/{user.id}/engineer.pdf",
        parsed_text=parsed_text,
    )
    db_session.add(cv)
    db_session.commit()
    db_session.refresh(cv)
    return cv


def test_suggest_titles_returns_valid_fake_llm_payload(api_test_db_session: Session) -> None:
    """Service returns structured titles when the fake LLM responds with 3-5 items."""
    user = create_test_user(api_test_db_session, email="service@example.com")
    cv = _seed_cv(api_test_db_session, user, parsed_text="Backend Python developer with FastAPI.")
    fake_llm = FakeLlmClient(
        response=TitleSuggestionsLlmOutput(
            titles=[
                SuggestedTitle(title="Python Developer", rationale="Strong Python focus."),
                SuggestedTitle(title="Backend Engineer", rationale="API and service work."),
                SuggestedTitle(title="FastAPI Engineer", rationale="Framework experience."),
            ]
        )
    )

    result = TitleSuggestionService(api_test_db_session, fake_llm).suggest_titles(user, cv)

    assert len(result.titles) == 3
    assert fake_llm.last_cv_text == "Backend Python developer with FastAPI."


def test_suggest_titles_rejects_missing_parsed_text(api_test_db_session: Session) -> None:
    """Service rejects CVs without parsed text before calling the LLM."""
    user = create_test_user(api_test_db_session, email="missing@example.com")
    cv = _seed_cv(api_test_db_session, user, parsed_text=None)
    fake_llm = FakeLlmClient(response=TitleSuggestionsLlmOutput(titles=[]))

    with pytest.raises(CvTextUnavailableError, match="CV text is not available"):
        TitleSuggestionService(api_test_db_session, fake_llm).suggest_titles(user, cv)

    assert fake_llm.last_cv_text is None


def test_suggest_titles_rejects_invalid_title_count(api_test_db_session: Session) -> None:
    """Service rejects malformed LLM payloads that do not contain 3-5 titles."""
    user = create_test_user(api_test_db_session, email="invalid@example.com")
    cv = _seed_cv(api_test_db_session, user, parsed_text="Product manager with SaaS experience.")
    fake_llm = FakeLlmClient(
        response=TitleSuggestionsLlmOutput(
            titles=[SuggestedTitle(title="Only One", rationale="Too few titles.")]
        )
    )

    with pytest.raises(TitleSuggestionResponseError, match="expected 3-5"):
        TitleSuggestionService(api_test_db_session, fake_llm).suggest_titles(user, cv)


def test_suggest_titles_propagates_llm_provider_errors(api_test_db_session: Session) -> None:
    """Provider failures bubble up without being swallowed by the service."""
    user = create_test_user(api_test_db_session, email="provider@example.com")
    cv = _seed_cv(api_test_db_session, user, parsed_text="DevOps engineer with Kubernetes.")
    fake_llm = FakeLlmClient(error=LlmClientError("provider timeout"))

    with pytest.raises(LlmClientError, match="provider timeout"):
        TitleSuggestionService(api_test_db_session, fake_llm).suggest_titles(user, cv)


def test_suggest_titles_appends_finops_audit_event(api_test_db_session: Session) -> None:
    """Successful suggestions append token and cost metadata to audit_log."""
    user = create_test_user(api_test_db_session, email="audit@example.com")
    cv = _seed_cv(api_test_db_session, user, parsed_text="Data analyst with SQL and Python.")
    fake_llm = FakeLlmClient(
        response=TitleSuggestionsLlmOutput(
            titles=[
                SuggestedTitle(title="Data Analyst", rationale="SQL reporting focus."),
                SuggestedTitle(title="Analytics Engineer", rationale="Pipeline experience."),
                SuggestedTitle(title="BI Developer", rationale="Dashboard delivery."),
            ]
        )
    )

    TitleSuggestionService(api_test_db_session, fake_llm).suggest_titles(user, cv)

    audit_entry = api_test_db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "ai.title_suggestion",
            AuditLogEntry.actor_user_id == user.id,
        )
    )
    assert audit_entry is not None
    assert audit_entry.metadata_json["cv_id"] == str(cv.id)
    assert "Data analyst" not in str(audit_entry.metadata_json)
