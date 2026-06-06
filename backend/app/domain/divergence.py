"""Divergence badge helpers for Job Match Results."""

from enum import StrEnum


class InterviewLikelihood(StrEnum):
    """AI estimate of screening competitiveness for a listing."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


from app.domain.validation import validate_match_score


def get_divergence_badge(
    *,
    match_score: int,
    interview_likelihood: InterviewLikelihood,
) -> str | None:
    """Return a divergence badge label when Match Score and Likelihood diverge.

    Threshold rules follow PRD § Divergence badge logic and ADR-0003.

    Args:
        match_score: Numeric CV-to-listing fit score (0–100).
        interview_likelihood: Categorical competitiveness estimate.

    Returns:
        str | None: Badge copy when thresholds match, otherwise None.

    Raises:
        ValueError: When match_score is outside the validated 0–100 range.
    """
    validated_score = validate_match_score(match_score)
    if validated_score >= 70 and interview_likelihood is InterviewLikelihood.LOW:
        return "Skills fit, seniority gap"
    if validated_score < 50 and interview_likelihood is InterviewLikelihood.HIGH:
        return "Competitive profile, weak keyword fit"
    return None
