"""Input validation helpers for infrastructure adapter boundaries."""

import json
import re
from typing import Any

from app.ports.blob_store import InvalidBlobKeyError
from app.ports.job_queue import InvalidQueueMessageError
from app.ports.secret_provider import InvalidSecretNameError

_SECRET_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


def validate_blob_logical_key(key: str) -> str:
    """Validate and normalize a blob logical key, rejecting path traversal.

    Azure blob names are opaque strings within a container; callers must not
    supply ``..`` segments that could escape a configured prefix scope.
    See: https://learn.microsoft.com/en-us/rest/api/storageservices/naming-and-referencing-containers--blobs--and-metadata

    Args:
        key: Caller-supplied logical key (e.g. ``user_id/uuid.pdf``).

    Returns:
        str: Normalized key without leading slashes.

    Raises:
        InvalidBlobKeyError: When the key is empty or contains unsafe segments.
    """
    if not key or not key.strip():
        raise InvalidBlobKeyError("Blob key must not be empty")

    normalized = key.strip().lstrip("/")
    if "\\" in normalized or "\x00" in normalized:
        raise InvalidBlobKeyError("Blob key contains invalid characters")

    segments = normalized.split("/")
    if any(segment in ("", ".", "..") for segment in segments):
        raise InvalidBlobKeyError("Blob key must not contain path traversal segments")

    return normalized


def validate_secret_name(name: str) -> str:
    """Validate a secret identifier before reading from the environment.

    Args:
        name: Expected environment variable name (e.g. ``OPENAI_API_KEY``).

    Returns:
        str: The validated secret name.

    Raises:
        InvalidSecretNameError: When the name is not a safe env-var identifier.
    """
    if not _SECRET_NAME_PATTERN.match(name):
        raise InvalidSecretNameError("Secret name must match ^[A-Z][A-Z0-9_]{0,127}$")
    return name


def validate_queue_message(message: dict[str, Any]) -> dict[str, Any]:
    """Validate a queue publish payload is a JSON-serializable object.

    Args:
        message: Message dict to enqueue.

    Returns:
        dict[str, Any]: The validated message.

    Raises:
        InvalidQueueMessageError: When the payload is not a JSON object.
    """
    if not isinstance(message, dict):
        raise InvalidQueueMessageError("Queue message must be a JSON object")
    try:
        json.dumps(message)
    except (TypeError, ValueError) as error:
        raise InvalidQueueMessageError("Queue message must be JSON-serializable") from error
    return message


def parse_queue_message_body(body: bytes) -> dict[str, Any]:
    """Parse and validate a UTF-8 JSON queue message body.

    Args:
        body: Raw message bytes from the broker.

    Returns:
        dict[str, Any]: Parsed JSON object payload.

    Raises:
        InvalidQueueMessageError: When the body is not valid JSON object text.
    """
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InvalidQueueMessageError("Queue message body must be valid UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise InvalidQueueMessageError("Queue message must be a JSON object")
    return payload
