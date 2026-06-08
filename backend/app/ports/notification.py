"""NotificationPort for transactional email delivery without provider coupling."""

from typing import Protocol


class NotificationPort(Protocol):
    """Port for sending transactional notifications such as magic-link emails."""

    def send_magic_link_email(self, *, to_email: str, verify_url: str) -> None:
        """Deliver a passwordless sign-in link to the requested email address.

        Args:
            to_email: Normalized recipient email address.
            verify_url: Absolute URL for ``GET /auth/magic-link/verify``.

        Raises:
            Exception: When the configured provider cannot send the message.
        """
        ...
