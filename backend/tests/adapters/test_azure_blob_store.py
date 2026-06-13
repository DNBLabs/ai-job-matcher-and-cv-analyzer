"""Contract + security tests for the Managed-Identity Azure Blob Store adapter.

A fake BlobServiceClient mimics the container/blob client tree so put/get/delete
semantics and key-prefix scoping are asserted without a live storage account.
"""

import pytest
from azure.core.exceptions import ResourceNotFoundError

from app.adapters.azure.blob_store import AzureBlobStore
from app.ports.blob_store import BlobNotFoundError, InvalidBlobKeyError


class _FakeBlobClient:
    def __init__(self, store: dict[str, bytes], name: str) -> None:
        self._store = store
        self._name = name

    def upload_blob(self, data: bytes, overwrite: bool = False) -> None:
        self._store[self._name] = data

    def download_blob(self):  # noqa: ANN201
        if self._name not in self._store:
            raise ResourceNotFoundError(self._name)
        data = self._store[self._name]
        return _FakeDownload(data)

    def delete_blob(self) -> None:
        if self._name not in self._store:
            raise ResourceNotFoundError(self._name)
        del self._store[self._name]


class _FakeDownload:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def readall(self) -> bytes:
        return self._data


class _FakeContainerClient:
    def __init__(self, store: dict[str, bytes]) -> None:
        self._store = store
        self.created = False

    def exists(self) -> bool:
        return True

    def create_container(self) -> None:
        self.created = True

    def get_blob_client(self, name: str) -> _FakeBlobClient:
        return _FakeBlobClient(self._store, name)


class _FakeServiceClient:
    """Captures the blob name tree and the account_url it was built with."""

    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}
        self._container = _FakeContainerClient(self.store)

    def get_container_client(self, container_name: str) -> _FakeContainerClient:
        return self._container


def _blob_store() -> tuple[AzureBlobStore, _FakeServiceClient]:
    service = _FakeServiceClient()
    store = AzureBlobStore(container_name="cvs", key_prefix="cvs/", service_client=service)
    return store, service


def test_put_and_get_round_trip() -> None:
    store, _ = _blob_store()
    store.put("user-1/cv-abc.pdf", b"%PDF-1.4 data")
    assert store.get("user-1/cv-abc.pdf") == b"%PDF-1.4 data"


def test_get_missing_raises_blob_not_found() -> None:
    store, _ = _blob_store()
    with pytest.raises(BlobNotFoundError):
        store.get("user-1/missing.pdf")


def test_delete_removes_object() -> None:
    store, _ = _blob_store()
    store.put("user-2/cv.pdf", b"bytes")
    store.delete("user-2/cv.pdf")
    with pytest.raises(BlobNotFoundError):
        store.get("user-2/cv.pdf")


def test_key_prefix_is_applied_to_blob_name() -> None:
    store, service = _blob_store()
    store.put("user-3/cv.pdf", b"scoped")
    assert "cvs/user-3/cv.pdf" in service.store


def test_unsafe_key_rejected_at_boundary() -> None:
    store, _ = _blob_store()
    with pytest.raises(InvalidBlobKeyError):
        store.put("../escape.pdf", b"x")
