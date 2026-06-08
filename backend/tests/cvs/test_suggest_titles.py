"""Integration tests for POST /cvs/{id}/suggest-titles."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.cvs import get_llm_client
from app.db.models import AuditLogEntry, Cv
from app.domain.title_suggestion import SuggestedTitle, TitleSuggestionsLlmOutput
from app.ports.llm_client import LlmClientError
from tests.cvs.test_cv_list_delete import _upload_cv
from tests.cvs.test_cv_upload import _authenticate_client
from tests.fakes.fake_llm_client import FakeLlmClient


def _valid_llm_titles() -> TitleSuggestionsLlmOutput:
    """Return a PRD-compliant fake LLM payload with three title suggestions."""
    return TitleSuggestionsLlmOutput(
        titles=[
            SuggestedTitle(title="Frontend Developer", rationale="Strong React experience."),
            SuggestedTitle(title="UI Engineer", rationale="Design-system and CSS depth."),
            SuggestedTitle(title="React Engineer", rationale="Component architecture focus."),
        ]
    )


@pytest.fixture
def suggest_titles_test_app(cv_test_app):
    """Extend the CV test app with a fake LLM client override."""
    fake_llm = FakeLlmClient(response=_valid_llm_titles())
    cv_test_app.state.fake_llm = fake_llm
    cv_test_app.dependency_overrides[get_llm_client] = lambda: fake_llm
    return cv_test_app


@pytest.fixture
async def suggest_titles_client(suggest_titles_test_app) -> AsyncClient:
    """Async HTTP client bound to the title suggestion test application."""
    from httpx import ASGITransport

    transport = ASGITransport(app=suggest_titles_test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


async def _set_cv_parsed_text(db_session: Session, cv: Cv, text: str) -> None:
    """Persist parsed CV text required for title suggestions."""
    cv.parsed_text = text
    db_session.commit()
    db_session.refresh(cv)


@pytest.mark.asyncio
async def test_suggest_titles_returns_structured_titles_for_owned_cv(
    suggest_titles_client: AsyncClient,
    suggest_titles_test_app,
    db_session: Session,
) -> None:
    """Authenticated owner receives 3-5 title suggestions derived from parsed CV text."""
    from tests.auth.conftest import create_test_user

    user = create_test_user(db_session, email="titles@example.com")

    cv_row = await _upload_cv(suggest_titles_client, db_session, user)
    await _set_cv_parsed_text(db_session, cv_row, "Senior React engineer with TypeScript experience.")

    response = await suggest_titles_client.post(f"/cvs/{cv_row.id}/suggest-titles")

    assert response.status_code == 200
    body = response.json()
    assert len(body["titles"]) == 3
    assert body["titles"][0] == {
        "title": "Frontend Developer",
        "rationale": "Strong React experience.",
    }

    fake_llm: FakeLlmClient = suggest_titles_test_app.state.fake_llm
    assert fake_llm.last_cv_text == "Senior React engineer with TypeScript experience."


@pytest.mark.asyncio
async def test_suggest_titles_without_session_returns_401(suggest_titles_client: AsyncClient) -> None:
    """Unauthenticated title suggestion requests are rejected."""
    response = await suggest_titles_client.post(f"/cvs/{uuid.uuid4()}/suggest-titles")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


@pytest.mark.asyncio
async def test_suggest_titles_for_foreign_cv_returns_404(
    suggest_titles_client: AsyncClient,
    db_session: Session,
) -> None:
    """Cross-account CV identifiers return a generic 404."""
    from tests.auth.conftest import create_test_user

    owner = create_test_user(db_session, email="owner@example.com")
    other = create_test_user(db_session, email="other@example.com")
    cv_row = await _upload_cv(suggest_titles_client, db_session, owner)
    await _set_cv_parsed_text(db_session, cv_row, "Backend Python developer.")

    _authenticate_client(suggest_titles_client, db_session, other)
    response = await suggest_titles_client.post(f"/cvs/{cv_row.id}/suggest-titles")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not found"}


@pytest.mark.asyncio
async def test_suggest_titles_without_parsed_text_returns_400(
    suggest_titles_client: AsyncClient,
    db_session: Session,
) -> None:
    """CVs without parsed text cannot request title suggestions."""
    from tests.auth.conftest import create_test_user

    user = create_test_user(db_session, email="notext@example.com")
    cv_row = await _upload_cv(suggest_titles_client, db_session, user)
    cv_row.parsed_text = None
    db_session.commit()

    response = await suggest_titles_client.post(f"/cvs/{cv_row.id}/suggest-titles")

    assert response.status_code == 400
    assert response.json() == {"detail": "CV text is not available for title suggestions"}


@pytest.mark.asyncio
async def test_suggest_titles_logs_finops_metadata_without_cv_content(
    suggest_titles_client: AsyncClient,
    db_session: Session,
) -> None:
    """Successful suggestions append FinOps audit metadata without CV body content."""
    from tests.auth.conftest import create_test_user

    user = create_test_user(db_session, email="finops@example.com")
    cv_row = await _upload_cv(suggest_titles_client, db_session, user)
    await _set_cv_parsed_text(db_session, cv_row, "Data engineer with Spark and Python.")

    response = await suggest_titles_client.post(f"/cvs/{cv_row.id}/suggest-titles")
    assert response.status_code == 200

    audit_entry = db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "ai.title_suggestion",
            AuditLogEntry.actor_user_id == user.id,
        )
    )
    assert audit_entry is not None
    metadata = audit_entry.metadata_json
    assert metadata["cv_id"] == str(cv_row.id)
    assert metadata["model"] == "gpt-4o-mini"
    assert metadata["prompt_tokens"] == 120
    assert metadata["completion_tokens"] == 45
    assert isinstance(metadata["estimated_usd"], float)
    assert "Senior React" not in str(metadata)
    assert "Data engineer" not in str(metadata)


@pytest.mark.asyncio
async def test_suggest_titles_handles_malformed_llm_response(
    suggest_titles_test_app,
    suggest_titles_client: AsyncClient,
    db_session: Session,
) -> None:
    """Malformed LLM output returns a generic 502 without leaking provider details."""
    from tests.auth.conftest import create_test_user

    fake_llm = FakeLlmClient(
        response=TitleSuggestionsLlmOutput(
            titles=[
                SuggestedTitle(title="Only One", rationale="Too few titles."),
            ]
        )
    )
    suggest_titles_test_app.state.fake_llm = fake_llm
    suggest_titles_test_app.dependency_overrides[get_llm_client] = lambda: fake_llm

    user = create_test_user(db_session, email="malformed@example.com")
    cv_row = await _upload_cv(suggest_titles_client, db_session, user)
    await _set_cv_parsed_text(db_session, cv_row, "Product manager with SaaS background.")

    response = await suggest_titles_client.post(f"/cvs/{cv_row.id}/suggest-titles")

    assert response.status_code == 502
    assert response.json() == {"detail": "Title suggestions are temporarily unavailable"}


@pytest.mark.asyncio
async def test_suggest_titles_handles_llm_provider_failure(
    suggest_titles_test_app,
    suggest_titles_client: AsyncClient,
    db_session: Session,
) -> None:
    """Upstream LLM failures return a generic 502 response."""
    from tests.auth.conftest import create_test_user

    fake_llm = FakeLlmClient(error=LlmClientError("provider timeout"))
    suggest_titles_test_app.state.fake_llm = fake_llm
    suggest_titles_test_app.dependency_overrides[get_llm_client] = lambda: fake_llm

    user = create_test_user(db_session, email="provider@example.com")
    cv_row = await _upload_cv(suggest_titles_client, db_session, user)
    await _set_cv_parsed_text(db_session, cv_row, "DevOps engineer with Kubernetes skills.")

    response = await suggest_titles_client.post(f"/cvs/{cv_row.id}/suggest-titles")

    assert response.status_code == 502
    assert response.json() == {"detail": "Title suggestions are temporarily unavailable"}
