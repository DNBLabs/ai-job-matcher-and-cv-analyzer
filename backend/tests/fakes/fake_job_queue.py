"""In-memory JobQueue fake for service-level tests."""

from typing import Any

from app.ports.job_queue import JobQueue


class FakeJobQueue:
    """Records published queue messages for orchestrator tests."""

    def __init__(self) -> None:
        """Initialize an empty published-message log."""
        self.published_messages: list[dict[str, Any]] = []

    def publish(self, message: dict[str, Any]) -> None:
        """Append a message to the published log."""
        self.published_messages.append(message)

    def consume(self, handler) -> None:
        """Drain published messages through the handler (JobQueue contract)."""
        while self.published_messages:
            handler(self.published_messages.pop(0))
