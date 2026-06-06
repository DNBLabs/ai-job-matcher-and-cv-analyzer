"""Shared input validation for domain boundaries (email, scores)."""

import json
import re
from typing import Any

# RFC 5321 limits the email local+domain storage to 320 characters.
# Source: https://datatracker.ietf.org/doc/html/rfc5321#section-4.5.3
_EMAIL_MAX_LENGTH = 320
_EMAIL_PATTERN = re.compile(r"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$")
_MATCH_SCORE_MIN = 0
_MATCH_SCORE_MAX = 100


def normalize_email(email: str) -> str:
    """Normalize and validate an email address for persistence lookups.

    Args:
        email: Raw email from CLI, OAuth, or magic-link request.

    Returns:
        str: Lowercased, trimmed email safe for database storage.

    Raises:
        ValueError: When the email is empty, too long, or malformed.
    """
    if not email or not email.strip():
        raise ValueError("email must not be empty")

    normalized = email.strip().lower()
    if len(normalized) > _EMAIL_MAX_LENGTH:
        raise ValueError("email exceeds maximum length")
    if any(character in normalized for character in ("\x00", "\n", "\r", "<", ">")):
        raise ValueError("email contains invalid characters")
    if not _EMAIL_PATTERN.match(normalized):
        raise ValueError("email format is invalid")
    return normalized


def validate_match_score(score: int) -> int:
    """Validate a Match Score is an integer within the PRD 0–100 range.

    Args:
        score: Numeric fit score from AI scoring or API input.

    Returns:
        int: The validated score.

    Raises:
        ValueError: When the score is not an integer in the allowed range.
    """
    if isinstance(score, bool) or not isinstance(score, int):
        raise ValueError("match_score must be an integer")
    if score < _MATCH_SCORE_MIN or score > _MATCH_SCORE_MAX:
        raise ValueError("match_score must be between 0 and 100 inclusive")
    return score


def validate_audit_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Ensure audit metadata is a JSON-serializable object without odd types.

    Args:
        metadata: Structured context for an append-only audit event.

    Returns:
        dict[str, Any]: Validated metadata dictionary.

    Raises:
        ValueError: When metadata is not a JSON object.
    """
    if not isinstance(metadata, dict):
        raise ValueError("audit metadata must be a JSON object")
    try:
        json.dumps(metadata)
    except (TypeError, ValueError) as error:
        raise ValueError("audit metadata must be JSON-serializable") from error
    return metadata
