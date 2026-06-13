"""Contract + security tests for the Azure Service Bus JobQueue adapter.

A fake ServiceBusClient mimics the sender/receiver context managers so publish
and consume round-trips are asserted without a live Service Bus namespace.
"""

import pytest

from app.adapters.azure.service_bus_queue import ServiceBusJobQueue
from app.ports.job_queue import InvalidQueueMessageError


class _FakeReceivedMessage:
    def __init__(self, body: str) -> None:
        self._body = body

    def __str__(self) -> str:
        return self._body


class _FakeSender:
    def __init__(self, sent: list) -> None:
        self._sent = sent

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None

    def send_messages(self, message) -> None:
        self._sent.append(str(message))


class _FakeReceiver:
    def __init__(self, batches: list[list[_FakeReceivedMessage]], completed: list) -> None:
        self._batches = batches
        self._completed = completed

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None

    def receive_messages(self, max_message_count: int = 1, max_wait_time=None):
        if self._batches:
            return self._batches.pop(0)
        return []

    def complete_message(self, message) -> None:
        self._completed.append(str(message))


class _FakeServiceBusClient:
    def __init__(self, batches=None) -> None:
        self.sent: list[str] = []
        self.completed: list[str] = []
        self._batches = batches or []
        self.closed = False

    def get_queue_sender(self, queue_name: str) -> _FakeSender:
        return _FakeSender(self.sent)

    def get_queue_receiver(self, queue_name: str, max_wait_time=None) -> _FakeReceiver:
        return _FakeReceiver(self._batches, self.completed)

    def close(self) -> None:
        self.closed = True


def test_publish_serializes_message_to_json_body() -> None:
    """publish sends a single Service Bus message carrying the JSON payload."""
    client = _FakeServiceBusClient()
    queue = ServiceBusJobQueue(queue_name="analysis-runs", client=client)

    queue.publish({"analysis_run_id": "run-1"})

    assert client.sent == ['{"analysis_run_id": "run-1"}']


def test_publish_rejects_non_object_payload() -> None:
    """publish enforces the JSON-object boundary before touching Service Bus."""
    client = _FakeServiceBusClient()
    queue = ServiceBusJobQueue(queue_name="analysis-runs", client=client)

    with pytest.raises(InvalidQueueMessageError):
        queue.publish(["not", "a", "dict"])  # type: ignore[arg-type]

    assert client.sent == []


def test_consume_parses_body_and_completes_message() -> None:
    """consume delivers parsed payloads to the handler and settles each message."""
    msg = _FakeReceivedMessage('{"analysis_run_id": "run-9"}')
    client = _FakeServiceBusClient(batches=[[msg]])
    queue = ServiceBusJobQueue(queue_name="analysis-runs", client=client)
    received: list[dict] = []

    queue.consume(received.append)

    assert received == [{"analysis_run_id": "run-9"}]
    assert client.completed == ['{"analysis_run_id": "run-9"}']


def test_consume_stops_when_queue_drains() -> None:
    """consume returns once the queue yields an empty batch (scale-to-zero exit)."""
    client = _FakeServiceBusClient(batches=[[_FakeReceivedMessage('{"a": 1}')]])
    queue = ServiceBusJobQueue(queue_name="analysis-runs", client=client)

    queue.consume(lambda _m: None)  # returns rather than blocking forever
