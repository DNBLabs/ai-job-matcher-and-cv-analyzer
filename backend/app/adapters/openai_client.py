"""OpenAI adapter implementing the LlmClient port for title suggestions."""

from openai import APIError, OpenAI

from app.domain.scoring_schema import ScoringLlmOutput
from app.domain.title_suggestion import TitleSuggestionsLlmOutput
from app.job_sources.base import NormalisedListing
from app.ports.llm_client import LlmClientError, LlmUsage

_TITLE_SYSTEM_PROMPT = (
    "You suggest UK job titles for a Job Seeker based only on their CV text. "
    "Return 3 to 5 concise, realistic role titles with one-sentence rationales. "
    "Do not invent employers, certifications, or experience not supported by the CV."
)

_SCORING_SYSTEM_PROMPT = (
    "You score how well a Job Seeker's CV fits a single UK job listing. "
    "Return match_score (0-100 integer) measuring requirement alignment, "
    "interview_likelihood (high/medium/low) estimating screening competitiveness, "
    "and breakdown arrays: matched_skills, skill_gaps, red_flags, talking_points. "
    "interview_likelihood is an estimate, not a guarantee. "
    "Use only evidence in the CV and listing; do not invent experience."
)


class OpenAiLlmClient:
    """OpenAI-backed LLM client using structured chat completion parsing."""

    def __init__(self, *, api_key: str, title_model: str, scoring_model: str) -> None:
        """Bind the adapter to an API key and the title and scoring model names.

        Args:
            api_key: OpenAI API key resolved from SecretProvider.
            title_model: Chat model for title suggestions (e.g. ``gpt-4o-mini``).
            scoring_model: Chat model for per-listing scoring (e.g. ``gpt-4o``).
        """
        self._client = OpenAI(api_key=api_key)
        self._model = title_model
        self._scoring_model = scoring_model

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

    def score_listing(
        self, *, cv_text: str, listing: NormalisedListing
    ) -> tuple[ScoringLlmOutput, LlmUsage]:
        """Call OpenAI with structured output parsing to score one listing.

        Args:
            cv_text: Parsed CV plain text forwarded to the model.
            listing: Normalised listing evaluated against the CV.

        Returns:
            tuple[ScoringLlmOutput, LlmUsage]: Validated scoring payload and usage.

        Raises:
            LlmClientError: When the provider fails or returns unusable output.
        """
        listing_prompt = (
            f"Job title: {listing.title}\n"
            f"Company: {listing.company}\n"
            f"Location: {listing.location}\n"
            f"Description:\n{listing.description}"
        )
        try:
            # Source: https://github.com/openai/openai-python/blob/main/helpers.md
            completion = self._client.chat.completions.parse(
                model=self._scoring_model,
                messages=[
                    {"role": "system", "content": _SCORING_SYSTEM_PROMPT},
                    {"role": "user", "content": f"CV:\n{cv_text}\n\nListing:\n{listing_prompt}"},
                ],
                response_format=ScoringLlmOutput,
            )
        except APIError as error:
            raise LlmClientError("OpenAI API request failed") from error

        message = completion.choices[0].message
        if message.refusal:
            raise LlmClientError("OpenAI refused the scoring request")
        if message.parsed is None:
            raise LlmClientError("OpenAI returned an unparsable scoring payload")

        usage = completion.usage
        if usage is None:
            raise LlmClientError("OpenAI response omitted token usage metadata")

        return message.parsed, LlmUsage(
            model=self._scoring_model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
        )
