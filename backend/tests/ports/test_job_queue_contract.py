"""Contract tests for JobQueue port implementations."""

import pytest

from app.ports.job_queue import JobQueue


def test_publish_and_consume_json_round_trip(job_queue: JobQueue) -> None:
    """JobQueue delivers a published JSON-serializable payload to the consume handler."""
    received: list[dict[str, str]] = []

    def handler(message: dict) -> None:
        received.append(message)

    job_queue.publish({"analysis_run_id": "run-123"})
    job_queue.consume(handler)

    assert received == [{"analysis_run_id": "run-123"}]


def test_consume_processes_messages_in_publish_order(job_queue: JobQueue) -> None:
    """JobQueue preserves FIFO order when multiple messages are pending."""
    received: list[str] = []

    def handler(message: dict) -> None:
        received.append(message["analysis_run_id"])

    job_queue.publish({"analysis_run_id": "first"})
    job_queue.publish({"analysis_run_id": "second"})
    job_queue.consume(handler)

    assert received == ["first", "second"]
