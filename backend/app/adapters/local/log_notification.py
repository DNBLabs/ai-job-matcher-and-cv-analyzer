"""Local NotificationPort adapter that logs outbound messages instead of sending email."""

import logging

from app.ports.notification import NotificationPort

logger = logging.getLogger(__name__)


class LogNotificationPort:
    """Write magic-link emails to application logs for local development."""

    def send_magic_link_email(self, *, to_email: str, verify_url: str) -> None:
        """Log a magic-link email without calling an external provider.

        Args:
            to_email: Normalized recipient email address.
            verify_url: Absolute verification URL containing the single-use token.
        """
        logger.info(
            "magic_link_email_sent",
            extra={"to_email": to_email, "verify_url": verify_url},
        )
