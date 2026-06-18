"""Worker entrypoint — consumes Analysis Run jobs from the queue and processes them."""

import logging
import signal
import sys
from typing import Any

from app.adapters.factory import (
    create_adzuna_job_source,
    create_job_queue,
    create_notification_port,
    create_reed_job_source,
    create_scoring_llm_client,
    create_secret_provider,
)
from app.ports.secret_provider import SecretNotFoundError
from app.config import get_settings
from app.db.session import get_session_factory
from app.services.scoring_service import ScoringService
from worker.handlers.analysis_run import handle_analysis_run_message
from worker.pipeline import AnalysisRunPipeline

logger = logging.getLogger(__name__)


def _install_sigterm_handler() -> None:
    """Raise KeyboardInterrupt on SIGTERM so pika's consume loop shuts down cleanly.

    pika's BlockingChannel.start_consuming() already catches KeyboardInterrupt and
    calls stop_consuming(). Mapping SIGTERM to KeyboardInterrupt lets Docker / Kubernetes
    stop signals flow through the existing pika shutdown path without a dedicated
    stop() method on the queue adapter.
    """

    def _handle(signum: int, frame: object) -> None:
        logger.info("worker received SIGTERM — initiating graceful shutdown")
        raise KeyboardInterrupt()

    signal.signal(signal.SIGTERM, _handle)


def startup_worker() -> str:
    """Initialize the worker process and confirm it is ready to consume jobs.

    Returns:
        str: Literal ``ready`` when startup checks succeed.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [worker] %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("azure").setLevel(logging.WARNING)
    logger.info("worker ready")
    return "ready"


def main() -> None:
    """Run the worker process until interrupted or SIGTERM received."""
    startup_worker()
    _install_sigterm_handler()

    settings = get_settings()
    session_factory = get_session_factory(settings)
    job_queue = create_job_queue(settings)

    secret_provider = create_secret_provider(settings)
    job_sources = []
    try:
        job_sources.append(("adzuna", create_adzuna_job_source(secret_provider)))
    except SecretNotFoundError:
        logger.warning("ADZUNA_APP_ID/KEY not configured — skipping Adzuna source")
    try:
        job_sources.append(("reed", create_reed_job_source(secret_provider)))
    except SecretNotFoundError:
        logger.warning("REED_API_KEY not configured — skipping Reed source")
    pipeline = AnalysisRunPipeline(
        job_sources=job_sources,
        scoring_service=ScoringService(create_scoring_llm_client(settings, secret_provider)),
        notification_port=create_notification_port(settings, secret_provider),
        frontend_base_url=settings.frontend_base_url,
    )

    def process_message(message: dict[str, Any]) -> None:
        """Open a session-per-message, process, and always close on exit.

        Args:
            message: Deserialized JSON payload delivered by the job queue.
        """
        session = session_factory()
        try:
            handle_analysis_run_message(message, session, pipeline=pipeline)
        except Exception:
            # Catch-all ensures pika acks the message rather than requeuing
            # indefinitely. The error is logged with traceback for investigation.
            logger.exception("unhandled error processing analysis run message — acking")
            session.rollback()
        finally:
            session.close()

    logger.info("worker consuming from queue")
    job_queue.consume(process_message)
    logger.info("worker stopped")


if __name__ == "__main__":
    main()
    sys.exit(0)
