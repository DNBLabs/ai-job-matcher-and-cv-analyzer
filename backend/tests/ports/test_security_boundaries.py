"""Security-focused contract tests for infrastructure port boundaries."""

import pytest

from app.ports.blob_store import BlobStore, InvalidBlobKeyError
from app.ports.job_queue import InvalidQueueMessageError, JobQueue
from app.ports.secret_provider import InvalidSecretNameError, SecretProvider


@pytest.mark.parametrize(
    "unsafe_key",
    ["", "../other-user/cv.pdf", "user-1/../../secret.pdf", "user-1\\cv.pdf"],
)
def test_blob_store_rejects_unsafe_keys(blob_store: BlobStore, unsafe_key: str) -> None:
    """BlobStore rejects path traversal and malformed keys at the adapter boundary."""
    with pytest.raises(InvalidBlobKeyError):
        blob_store.put(unsafe_key, b"payload")


def test_secret_provider_rejects_invalid_secret_names(secret_provider: SecretProvider) -> None:
    """SecretProvider rejects names that are not safe environment variable identifiers."""
    with pytest.raises(InvalidSecretNameError):
        secret_provider.get("openai-api-key")


def test_job_queue_rejects_non_object_publish_payload(job_queue: JobQueue) -> None:
    """JobQueue rejects publish payloads that are not JSON objects."""
    with pytest.raises(InvalidQueueMessageError):
        job_queue.publish(["not", "a", "dict"])  # type: ignore[arg-type]
