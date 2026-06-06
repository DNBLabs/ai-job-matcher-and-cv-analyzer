"""In-process JobQueue adapter for contract tests and local development."""

from collections.abc import Callable
from typing import Any

from app.adapters.boundary_validation import validate_queue_message


class InProcessJobQueue:
    """FIFO queue that stores JSON messages in memory within the current process."""

    def __init__(self) -> None:
        """Initialize an empty pending message queue."""
        self._pending_messages: list[dict[str, Any]] = []

    def publish(self, message: dict[str, Any]) -> None:
        """Append a JSON-compatible message to the pending queue."""
        self._pending_messages.append(validate_queue_message(message))

    def consume(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Drain all pending messages and invoke ``handler`` for each."""
        while self._pending_messages:
            handler(self._pending_messages.pop(0))
