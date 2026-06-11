"""Pure transactional email templates for magic-link and run-completion mail.

Templates are provider-agnostic: each builder takes a URL and returns an
``EmailContent`` (subject + HTML + plain text). Adapters (log, Resend) render
these and deliver them, so subject/body structure is testable without sending.

No CV text, prompts, or tokens beyond the supplied URL are ever embedded
(CONTEXT §3): the magic-link token lives only inside ``verify_url``, and the
run-completion deep link carries no share token — it relies on the owner
signing in (CONTEXT §3 "no public or signed share URLs in MVP").
"""

from dataclasses import dataclass

MAGIC_LINK_SUBJECT = "Sign in to AI Job Matcher"
RUN_COMPLETE_SUBJECT = "Your job matches are ready"


@dataclass(frozen=True)
class EmailContent:
    """Rendered transactional email payload ready for any delivery adapter."""

    subject: str
    html: str
    text: str


def render_magic_link_email(*, verify_url: str) -> EmailContent:
    """Render the passwordless sign-in email containing the verification link.

    Args:
        verify_url: Absolute single-use ``/auth/magic-link/verify`` URL.

    Returns:
        EmailContent: Subject with matching HTML and plain-text bodies.
    """
    text = (
        "Sign in to AI Job Matcher\n\n"
        "Use the link below to sign in. It can only be used once and expires "
        "in 15 minutes:\n\n"
        f"{verify_url}\n\n"
        "If you did not request this, you can ignore this email."
    )
    html = (
        "<h1>Sign in to AI Job Matcher</h1>"
        "<p>Use the button below to sign in. It can only be used once and "
        "expires in 15 minutes.</p>"
        f'<p><a href="{verify_url}">Sign in</a></p>'
        f"<p>Or paste this link into your browser:<br>{verify_url}</p>"
        "<p>If you did not request this, you can ignore this email.</p>"
    )
    return EmailContent(subject=MAGIC_LINK_SUBJECT, html=html, text=text)


def render_run_complete_email(*, results_url: str) -> EmailContent:
    """Render the run-completion email linking to the owner's results page.

    Args:
        results_url: Absolute deep link to the run results (no share token).

    Returns:
        EmailContent: Subject with matching HTML and plain-text bodies.
    """
    text = (
        "Your job matches are ready\n\n"
        "Your Analysis Run has finished. Sign in and open your results here:\n\n"
        f"{results_url}\n\n"
        "You must be signed in as the account that started the run to view them."
    )
    html = (
        "<h1>Your job matches are ready</h1>"
        "<p>Your Analysis Run has finished. Sign in and open your results "
        "using the button below.</p>"
        f'<p><a href="{results_url}">View your matches</a></p>'
        f"<p>Or paste this link into your browser:<br>{results_url}</p>"
        "<p>You must be signed in as the account that started the run to "
        "view them.</p>"
    )
    return EmailContent(subject=RUN_COMPLETE_SUBJECT, html=html, text=text)
