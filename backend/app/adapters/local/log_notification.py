"""Local NotificationPort adapter that logs outbound messages instead of sending email."""

import logging

from app.notifications.templates import render_magic_link_email, render_run_complete_email

logger = logging.getLogger(__name__)


class LogNotificationPort:
    """Write transactional emails to application logs for local development."""

    def send_magic_link_email(self, *, to_email: str, verify_url: str) -> None:
        """Log a magic-link email without calling an external provider.

        Args:
            to_email: Normalized recipient email address.
            verify_url: Absolute verification URL containing the single-use token.
        """
        content = render_magic_link_email(verify_url=verify_url)
        logger.info(
            "magic_link_email_sent",
            extra={"to_email": to_email, "subject": content.subject, "verify_url": verify_url},
        )

    def send_run_complete_email(self, *, to_email: str, results_url: str) -> None:
        """Log a run-completion email without calling an external provider.

        Args:
            to_email: Run owner's email address.
            results_url: Absolute results deep link (no share token).
        """
        content = render_run_complete_email(results_url=results_url)
        logger.info(
            "run_complete_email_sent",
            extra={"to_email": to_email, "subject": content.subject, "results_url": results_url},
        )
