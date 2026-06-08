"""In-memory LlmClient fake for deterministic title suggestion tests."""

from app.domain.title_suggestion import TitleSuggestionsLlmOutput
from app.ports.llm_client import LlmClientError, LlmUsage


class FakeLlmClient:
    """Deterministic LlmClient that returns configured title suggestions."""

    def __init__(
        self,
        *,
        response: TitleSuggestionsLlmOutput | None = None,
        error: Exception | None = None,
    ) -> None:
        """Configure the fake response or error raised on suggest_job_titles.

        Args:
            response: Structured titles returned to callers.
            error: Optional exception to raise instead of returning a response.
        """
        self._response = response
        self._error = error
        self.last_cv_text: str | None = None

    def suggest_job_titles(self, *, cv_text: str) -> tuple[TitleSuggestionsLlmOutput, LlmUsage]:
        """Record the CV text and return the configured suggestion payload.

        Args:
            cv_text: Parsed CV plain text forwarded to the model.

        Returns:
            tuple[TitleSuggestionsLlmOutput, LlmUsage]: Structured titles and token usage.

        Raises:
            LlmClientError: When the fake is configured to simulate provider failure.
            Exception: When a custom error instance was injected for the test case.
        """
        self.last_cv_text = cv_text
        if self._error is not None:
            raise self._error
        if self._response is None:
            raise LlmClientError("fake LLM has no configured response")
        return self._response, LlmUsage(
            model="gpt-4o-mini",
            prompt_tokens=120,
            completion_tokens=45,
        )
