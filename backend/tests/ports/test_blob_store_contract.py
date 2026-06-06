"""Contract tests for BlobStore port implementations."""

import pytest

from app.ports.blob_store import BlobNotFoundError, BlobStore


def test_put_and_get_round_trip(blob_store: BlobStore) -> None:
    """BlobStore stores bytes under a key and returns them on get."""
    payload = b"%PDF-1.4 test cv content"

    blob_store.put("user-1/cv-abc.pdf", payload)

    assert blob_store.get("user-1/cv-abc.pdf") == payload


def test_get_raises_when_object_missing(blob_store: BlobStore) -> None:
    """BlobStore.get raises BlobNotFoundError for unknown keys."""
    with pytest.raises(BlobNotFoundError):
        blob_store.get("user-1/missing.pdf")


def test_delete_removes_object(blob_store: BlobStore) -> None:
    """BlobStore.delete removes the object so subsequent get fails."""
    blob_store.put("user-2/cv-delete.pdf", b"delete-me")
    blob_store.delete("user-2/cv-delete.pdf")

    with pytest.raises(BlobNotFoundError):
        blob_store.get("user-2/cv-delete.pdf")


def test_key_prefix_is_applied_to_stored_objects(blob_store: BlobStore) -> None:
    """BlobStore with a key prefix scopes keys under that prefix internally."""
    blob_store.put("user-3/cv-prefix.pdf", b"scoped")

    assert blob_store.get("user-3/cv-prefix.pdf") == b"scoped"
