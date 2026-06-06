"""JobQueue port for async Analysis Run work dispatch without cloud SDK coupling."""

from collections.abc import Callable
from typing import Any, Protocol


class InvalidQueueMessageError(ValueError):
    """Raised when a queue message fails boundary validation."""


class JobQueue(Protocol):
    """Port for publishing and consuming JSON job messages."""

    def publish(self, message: dict[str, Any]) -> None:
        """Enqueue a JSON-serializable message for worker processing.

        Args:
            message: Payload dict (typically ``{"analysis_run_id": "<uuid>"}``).

        Raises:
            InvalidQueueMessageError: When the payload is not a JSON object.
        """
        ...

    def consume(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Invoke ``handler`` for each pending message.

        In-process adapters drain the pending queue once. RabbitMQ adapters block
        until interrupted, invoking ``handler`` per delivered message.

        Args:
            handler: Callback receiving the deserialized JSON payload.
        """
        ...
