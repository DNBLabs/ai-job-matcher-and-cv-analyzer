"""Behavior tests for Match Score vs Interview Likelihood divergence badges."""

from app.domain.divergence import InterviewLikelihood, get_divergence_badge


def test_high_match_with_low_likelihood_shows_seniority_gap_badge() -> None:
    """Strong skills fit with low competitiveness surfaces the seniority-gap badge."""
    badge = get_divergence_badge(match_score=75, interview_likelihood=InterviewLikelihood.LOW)

    assert badge == "Skills fit, seniority gap"


def test_low_match_with_high_likelihood_shows_keyword_fit_badge() -> None:
    """Competitive profile with weak keyword alignment surfaces the keyword-fit badge."""
    badge = get_divergence_badge(match_score=40, interview_likelihood=InterviewLikelihood.HIGH)

    assert badge == "Competitive profile, weak keyword fit"


def test_aligned_scores_return_no_badge() -> None:
    """When scores align, the results card shows no divergence badge."""
    assert get_divergence_badge(match_score=80, interview_likelihood=InterviewLikelihood.HIGH) is None
    assert get_divergence_badge(match_score=40, interview_likelihood=InterviewLikelihood.LOW) is None


def test_boundary_thresholds_apply_inclusively() -> None:
    """PRD thresholds at 70 and 50 are inclusive boundary checks."""
    assert get_divergence_badge(match_score=70, interview_likelihood=InterviewLikelihood.LOW) is not None
    assert get_divergence_badge(match_score=49, interview_likelihood=InterviewLikelihood.HIGH) is not None
