"""Snapshot-structure tests for transactional email templates (Task 19).

Templates are pure functions: given a URL they return subject + HTML + text with
no provider coupling, so their structure can be asserted without sending email.
"""

from app.notifications.templates import (
    render_magic_link_email,
    render_run_complete_email,
)

_VERIFY_URL = "https://api.example.com/auth/magic-link/verify?token=abc123"
_RESULTS_URL = "https://app.example.com/runs/11111111-1111-1111-1111-111111111111"


def test_magic_link_email_has_subject_and_both_bodies() -> None:
    """Magic-link template returns a fixed subject with HTML and plain-text bodies."""
    content = render_magic_link_email(verify_url=_VERIFY_URL)

    assert content.subject == "Sign in to AI Job Matcher"
    assert content.html.strip()
    assert content.text.strip()


def test_magic_link_email_embeds_verify_url_in_both_bodies() -> None:
    """The verification link appears verbatim in both the HTML and text bodies."""
    content = render_magic_link_email(verify_url=_VERIFY_URL)

    assert _VERIFY_URL in content.html
    assert _VERIFY_URL in content.text


def test_magic_link_email_states_single_use_expiry() -> None:
    """Body warns the link is single-use and time-limited (15-minute expiry)."""
    content = render_magic_link_email(verify_url=_VERIFY_URL)

    assert "15 minutes" in content.text
    assert "once" in content.text.lower()


def test_run_complete_email_has_subject_and_both_bodies() -> None:
    """Run-complete template returns a fixed subject with HTML and plain-text bodies."""
    content = render_run_complete_email(results_url=_RESULTS_URL)

    assert content.subject == "Your job matches are ready"
    assert content.html.strip()
    assert content.text.strip()


def test_run_complete_email_embeds_results_url_in_both_bodies() -> None:
    """The results deep link appears verbatim in both the HTML and text bodies."""
    content = render_run_complete_email(results_url=_RESULTS_URL)

    assert _RESULTS_URL in content.html
    assert _RESULTS_URL in content.text


def test_run_complete_email_requires_sign_in_and_carries_no_share_token() -> None:
    """Deep link relies on the owner signing in; it carries no public share token."""
    content = render_run_complete_email(results_url=_RESULTS_URL)

    assert "sign in" in content.text.lower()
    assert "token=" not in content.text
    assert "token=" not in content.html
