"""Queue message handler for Analysis Run status transitions."""

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.repositories.analysis_run_repository import AnalysisRunRepository
from app.domain.analysis_run import AnalysisRunStatus, can_transition

logger = logging.getLogger(__name__)


def _parse_run_id(message: dict[str, Any]) -> uuid.UUID | None:
    """Extract and validate the analysis_run_id field from a queue message.

    Args:
        message: Deserialized JSON payload from the job queue.

    Returns:
        uuid.UUID | None: Parsed run ID, or None when the field is absent or not a valid UUID.
    """
    raw_id = message.get("analysis_run_id")
    if not raw_id:
        logger.warning("queue message missing analysis_run_id field")
        return None
    try:
        return uuid.UUID(str(raw_id))
    except ValueError:
        logger.warning(
            "queue message has invalid analysis_run_id type: %s",
            type(raw_id).__name__,
        )
        return None


def handle_analysis_run_message(message: dict[str, Any], session: Session) -> None:
    """Transition an Analysis Run from Queued → Scraping → Scoring.

    Designed to be called per queue message. Logs and returns without raising
    on invalid or missing runs so the worker does not crash-loop on poison messages.
    Each transition is committed separately so partial progress is visible.

    Args:
        message: Deserialized JSON payload from the job queue.
        session: Active database session for loading and updating the run.
    """
    run_id = _parse_run_id(message)
    if run_id is None:
        return

    repository = AnalysisRunRepository(session)
    run = repository.get_by_id(run_id)
    if run is None:
        logger.warning("analysis run not found: %s", run_id)
        return

    if not can_transition(run.status, AnalysisRunStatus.SCRAPING):
        logger.warning(
            "analysis run %s in unexpected status %s — expected queued; skipping",
            run_id,
            run.status,
        )
        return

    run.status = AnalysisRunStatus.SCRAPING
    session.commit()
    logger.info("analysis run %s → scraping", run_id)

    run.status = AnalysisRunStatus.SCORING
    session.commit()
    logger.info("analysis run %s → scoring", run_id)
