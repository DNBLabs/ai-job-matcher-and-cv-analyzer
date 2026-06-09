"""Domain schemas for per-listing AI scoring (Match Score + Interview Likelihood).

Shapes the single structured LLM call per listing defined in ADR-0003: a Match
Score (0–100), an Interview Likelihood band, and the full breakdown arrays.
"""

from pydantic import BaseModel, Field

from app.domain.divergence import InterviewLikelihood


class ScoringLlmOutput(BaseModel):
    """Structured scoring payload returned by the LLM per listing.

    All fields are required so OpenAI strict Structured Outputs always populates
    them. Numeric range and enum semantics are enforced in the scoring service
    (``validate_match_score``) rather than via JSON-schema keywords the strict
    mode does not support.
    Source: https://platform.openai.com/docs/guides/structured-outputs
    """

    match_score: int
    interview_likelihood: InterviewLikelihood
    matched_skills: list[str]
    skill_gaps: list[str]
    red_flags: list[str]
    talking_points: list[str]

    def breakdown(self) -> dict[str, list[str]]:
        """Return the breakdown arrays for persistence in ``breakdown_json``.

        Returns:
            dict[str, list[str]]: Matched skills, gaps, red flags, and talking points.
        """
        return {
            "matched_skills": list(self.matched_skills),
            "skill_gaps": list(self.skill_gaps),
            "red_flags": list(self.red_flags),
            "talking_points": list(self.talking_points),
        }


class ScoredListing(BaseModel):
    """One scored listing pairing its source identity with the AI evaluation."""

    source: str
    title: str
    company: str
    url: str
    match_score: int = Field(..., ge=0, le=100)
    interview_likelihood: InterviewLikelihood
    breakdown_json: dict[str, list[str]]


class ScoringFinops(BaseModel):
    """Aggregated per-run token usage and estimated cost for FinOps logging."""

    model: str
    listings_scored: int
    listings_skipped: int
    prompt_tokens: int
    completion_tokens: int
    estimated_usd: float


class RunScoringResult(BaseModel):
    """Outcome of scoring a batch of listings within one Analysis Run."""

    scored: list[ScoredListing]
    finops: ScoringFinops
