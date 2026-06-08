"""LlmClient port for structured OpenAI completions without SDK coupling."""

from dataclasses import dataclass
from typing import Protocol

from app.domain.title_suggestion import TitleSuggestionsLlmOutput


class LlmClientError(Exception):
    """Raised when the configured LLM provider cannot return valid title suggestions."""


@dataclass(frozen=True)
class LlmUsage:
    """Token usage metadata returned by an LLM provider call."""

    model: str
    prompt_tokens: int
    completion_tokens: int


class LlmClient(Protocol):
    """Port for sync structured title suggestions derived from parsed CV text."""

    def suggest_job_titles(self, *, cv_text: str) -> tuple[TitleSuggestionsLlmOutput, LlmUsage]:
        """Generate structured job title suggestions from parsed CV plain text.

        Args:
            cv_text: Parsed CV text only; raw PDF bytes must never be passed.

        Returns:
            tuple[TitleSuggestionsLlmOutput, LlmUsage]: Validated titles and token usage.

        Raises:
            LlmClientError: When the provider fails or returns unusable output.
        """
        ...
