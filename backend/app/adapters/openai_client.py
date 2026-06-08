"""OpenAI adapter implementing the LlmClient port for title suggestions."""

from openai import APIError, OpenAI

from app.domain.title_suggestion import TitleSuggestionsLlmOutput
from app.ports.llm_client import LlmClientError, LlmUsage

_TITLE_SYSTEM_PROMPT = (
    "You suggest UK job titles for a Job Seeker based only on their CV text. "
    "Return 3 to 5 concise, realistic role titles with one-sentence rationales. "
    "Do not invent employers, certifications, or experience not supported by the CV."
)


class OpenAiLlmClient:
    """OpenAI-backed LlmClient using structured chat completion parsing."""

    def __init__(self, *, api_key: str, model: str) -> None:
        """Bind the adapter to an API key and title-suggestion model name.

        Args:
            api_key: OpenAI API key resolved from SecretProvider.
            model: Chat model identifier (e.g. ``gpt-4o-mini``).
        """
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def suggest_job_titles(self, *, cv_text: str) -> tuple[TitleSuggestionsLlmOutput, LlmUsage]:
        """Call OpenAI with structured output parsing for title suggestions.

        Args:
            cv_text: Parsed CV plain text forwarded to the model.

        Returns:
            tuple[TitleSuggestionsLlmOutput, LlmUsage]: Parsed titles and token usage.

        Raises:
            LlmClientError: When the provider fails or returns unusable output.
        """
        try:
            # Source: https://github.com/openai/openai-python/blob/main/helpers.md
            completion = self._client.chat.completions.parse(
                model=self._model,
                messages=[
                    {"role": "system", "content": _TITLE_SYSTEM_PROMPT},
                    {"role": "user", "content": cv_text},
                ],
                response_format=TitleSuggestionsLlmOutput,
            )
        except APIError as error:
            raise LlmClientError("OpenAI API request failed") from error

        message = completion.choices[0].message
        if message.refusal:
            raise LlmClientError("OpenAI refused the title suggestion request")
        if message.parsed is None:
            raise LlmClientError("OpenAI returned an unparsable title suggestion payload")

        usage = completion.usage
        if usage is None:
            raise LlmClientError("OpenAI response omitted token usage metadata")

        return message.parsed, LlmUsage(
            model=self._model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
        )
