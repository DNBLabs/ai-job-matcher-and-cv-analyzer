"""Shared put/get/delete logic for Azure Blob Storage adapters.

Both the local Azurite adapter (connection-string auth) and the production
adapter (Managed Identity auth) share identical object semantics and differ only
in how the ``BlobServiceClient`` is constructed. Centralising the data-plane code
here prevents drift between local and prod (ADR-0002 §Negative: "drift between
adapters is a testing burden").

Source: https://learn.microsoft.com/en-us/azure/storage/blobs/storage-quickstart-blobs-python
"""

from azure.core.exceptions import ResourceNotFoundError

from app.adapters.boundary_validation import validate_blob_logical_key
from app.ports.blob_store import BlobNotFoundError


class BlobServiceBlobStore:
    """BlobStore over a BlobServiceClient; subclasses supply the client.

    The service client may be injected directly (tests / production factory) or
    built lazily by a subclass overriding ``_build_service_client``.
    """

    def __init__(
        self,
        *,
        container_name: str,
        key_prefix: str = "",
        service_client=None,  # noqa: ANN001 — BlobServiceClient or a test double
    ) -> None:
        """Configure container, key prefix, and an optional pre-built service client.

        Args:
            container_name: Blob container name (e.g. ``cvs``).
            key_prefix: Optional prefix prepended to all logical keys.
            service_client: Pre-built BlobServiceClient-like object; when omitted the
                subclass builds one lazily on first use.
        """
        normalized_prefix = key_prefix.strip("/")
        self._key_prefix = f"{normalized_prefix}/" if normalized_prefix else ""
        self._container_name = container_name
        self._service_client = service_client
        self._container_client = None
        self._container_ready = False

    def _build_service_client(self):  # noqa: ANN202 — returns BlobServiceClient
        """Construct the BlobServiceClient. Overridden by subclasses."""
        raise NotImplementedError

    def _ensure_container(self) -> None:
        """Resolve the container client and create the container on first use."""
        if self._container_ready:
            return
        if self._service_client is None:
            self._service_client = self._build_service_client()
        self._container_client = self._service_client.get_container_client(self._container_name)
        if not self._container_client.exists():
            self._container_client.create_container()
        self._container_ready = True

    def _storage_key(self, key: str) -> str:
        """Return the prefix-scoped blob name for a validated logical key."""
        logical_key = validate_blob_logical_key(key)
        return f"{self._key_prefix}{logical_key}"

    def _blob_client(self, key: str):  # noqa: ANN202 — returns BlobClient
        """Return a BlobClient for the logical key."""
        assert self._container_client is not None
        return self._container_client.get_blob_client(self._storage_key(key))

    def put(self, key: str, data: bytes) -> None:
        """Upload bytes, overwriting any existing blob at the key."""
        self._ensure_container()
        self._blob_client(key).upload_blob(data, overwrite=True)

    def get(self, key: str) -> bytes:
        """Download blob bytes or raise BlobNotFoundError when missing."""
        self._ensure_container()
        try:
            return self._blob_client(key).download_blob().readall()
        except ResourceNotFoundError as error:
            raise BlobNotFoundError(f"Blob not found: {key}") from error

    def delete(self, key: str) -> None:
        """Delete the blob or raise BlobNotFoundError when missing."""
        self._ensure_container()
        try:
            self._blob_client(key).delete_blob()
        except ResourceNotFoundError as error:
            raise BlobNotFoundError(f"Blob not found: {key}") from error
