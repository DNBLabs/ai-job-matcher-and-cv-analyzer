"""Tests for the Analysis Run worker entrypoint."""

from worker.main import startup_worker


def test_worker_startup_signals_ready() -> None:
    """Worker startup reports ready before entering the consume loop."""
    assert startup_worker() == "ready"
