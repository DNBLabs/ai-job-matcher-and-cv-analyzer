"""Application service for sync AI Suggested Job Titles on owned CVs."""

from sqlalchemy.orm import Session

from app.db.models import Cv, UserAccount
from app.db.repositories.audit_log_repository import AuditLogRepository
from app.domain.finops import estimate_gpt4o_mini_usd
from app.domain.title_suggestion import TitleSuggestionResponse
from app.ports.llm_client import LlmClient, LlmClientError


class CvTextUnavailableError(ValueError):
    """Raised when a CV has no parsed text available for title suggestions."""


class TitleSuggestionResponseError(Exception):
    """Raised when the LLM returns an invalid title suggestion payload."""


class TitleSuggestionService:
    """Coordinate owner-scoped title suggestions, validation, and FinOps audit logging."""

    def __init__(self, session: Session, llm_client: LlmClient) -> None:
        """Bind the service to a database session and LLM port.

        Args:
            session: Request-scoped SQLAlchemy session.
            llm_client: Structured title suggestion provider.
        """
        self._session = session
        self._llm_client = llm_client

    def suggest_titles(self, user: UserAccount, cv: Cv) -> TitleSuggestionResponse:
        """Generate title suggestions from parsed CV text and log FinOps metadata.

        Args:
            user: Authenticated owner of the CV.
            cv: Owner-scoped CV row including parsed text.

        Returns:
            TitleSuggestionResponse: Three to five title suggestions with rationales.

        Raises:
            CvTextUnavailableError: When parsed CV text is missing or blank.
            TitleSuggestionResponseError: When the LLM payload fails PRD validation.
            LlmClientError: When the provider cannot complete the request.
        """
        cv_text = (cv.parsed_text or "").strip()
        if not cv_text:
            raise CvTextUnavailableError("CV text is not available for title suggestions")

        llm_output, usage = self._llm_client.suggest_job_titles(cv_text=cv_text)
        title_count = len(llm_output.titles)
        if title_count < 3 or title_count > 5:
            raise TitleSuggestionResponseError(
                f"expected 3-5 title suggestions, received {title_count}"
            )

        estimated_usd = estimate_gpt4o_mini_usd(
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
        )
        AuditLogRepository(self._session).append_event(
            event_type="ai.title_suggestion",
            actor_user_id=user.id,
            metadata={
                "cv_id": str(cv.id),
                "model": usage.model,
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "estimated_usd": estimated_usd,
            },
        )

        return TitleSuggestionResponse(titles=llm_output.titles)
