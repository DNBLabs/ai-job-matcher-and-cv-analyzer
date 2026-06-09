"""In-memory ScoringLlmClient fake for deterministic scoring service tests."""

from collections.abc import Sequence

from app.domain.scoring_schema import ScoringLlmOutput
from app.job_sources.base import NormalisedListing
from app.ports.llm_client import LlmClientError, LlmUsage


class FakeScoringLlmClient:
    """Deterministic ScoringLlmClient driven by a queued sequence of behaviours.

    Each call pops the next behaviour: an Exception is raised, otherwise the
    ScoringLlmOutput is returned with fixed token usage. When the queue is
    exhausted the last behaviour is reused so single-response tests stay terse.
    """

    def __init__(
        self,
        *,
        behaviours: Sequence[ScoringLlmOutput | Exception],
        model: str = "gpt-4o",
        prompt_tokens: int = 800,
        completion_tokens: int = 200,
    ) -> None:
        """Configure the ordered behaviours and token usage reported per call.

        Args:
            behaviours: Ordered outputs or exceptions returned on successive calls.
            model: Model name echoed in returned LlmUsage.
            prompt_tokens: Input tokens reported per successful call.
            completion_tokens: Output tokens reported per successful call.
        """
        if not behaviours:
            raise ValueError("FakeScoringLlmClient requires at least one behaviour")
        self._behaviours = list(behaviours)
        self._model = model
        self._prompt_tokens = prompt_tokens
        self._completion_tokens = completion_tokens
        self.call_count = 0
        self.seen_cv_texts: list[str] = []
        self.seen_listings: list[NormalisedListing] = []

    def score_listing(
        self, *, cv_text: str, listing: NormalisedListing
    ) -> tuple[ScoringLlmOutput, LlmUsage]:
        """Record inputs and return the next queued behaviour.

        Args:
            cv_text: Parsed CV plain text forwarded to the model.
            listing: Listing under evaluation.

        Returns:
            tuple[ScoringLlmOutput, LlmUsage]: Configured scoring payload and usage.

        Raises:
            Exception: When the next queued behaviour is an exception instance.
        """
        self.call_count += 1
        self.seen_cv_texts.append(cv_text)
        self.seen_listings.append(listing)

        index = min(self.call_count - 1, len(self._behaviours) - 1)
        behaviour = self._behaviours[index]
        if isinstance(behaviour, Exception):
            raise behaviour
        return behaviour, LlmUsage(
            model=self._model,
            prompt_tokens=self._prompt_tokens,
            completion_tokens=self._completion_tokens,
        )


def make_listing(*, source: str = "adzuna", external_id: str = "ext-1") -> NormalisedListing:
    """Build a NormalisedListing fixture for scoring tests.

    Args:
        source: Job Source identifier.
        external_id: Unused by the scoring service but kept for caller clarity.

    Returns:
        NormalisedListing: Minimal valid listing.
    """
    _ = external_id
    return NormalisedListing(
        title="Backend Engineer",
        company="Acme Ltd",
        location="London",
        url="https://example.com/jobs/1",
        description="Python, FastAPI, PostgreSQL.",
        source=source,
    )
