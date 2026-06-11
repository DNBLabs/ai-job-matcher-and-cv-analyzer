"""In-memory NotificationPort capturing transactional emails for tests."""


class FakeNotificationPort:
    """Record outbound emails instead of delivering them.

    Set ``raise_on_send`` to simulate a provider outage and assert the pipeline
    tolerates email-delivery failures without altering the run's terminal status.
    """

    def __init__(self, *, raise_on_send: bool = False) -> None:
        """Initialize empty capture lists.

        Args:
            raise_on_send: When True, every send raises to simulate provider failure.
        """
        self.magic_link_emails: list[dict[str, str]] = []
        self.run_complete_emails: list[dict[str, str]] = []
        self._raise_on_send = raise_on_send

    def send_magic_link_email(self, *, to_email: str, verify_url: str) -> None:
        """Record (or fail) a magic-link email."""
        if self._raise_on_send:
            raise RuntimeError("simulated provider outage")
        self.magic_link_emails.append({"to_email": to_email, "verify_url": verify_url})

    def send_run_complete_email(self, *, to_email: str, results_url: str) -> None:
        """Record (or fail) a run-completion email."""
        if self._raise_on_send:
            raise RuntimeError("simulated provider outage")
        self.run_complete_emails.append({"to_email": to_email, "results_url": results_url})
