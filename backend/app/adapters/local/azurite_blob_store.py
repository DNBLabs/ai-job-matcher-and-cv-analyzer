"""Azurite/Azure Blob Storage BlobStore adapter for local and production use."""

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobServiceClient

from app.adapters.boundary_validation import validate_blob_logical_key
from app.ports.blob_store import BlobNotFoundError


class AzuriteBlobStore:
    """BlobStore backed by Azure Blob Storage or the Azurite emulator.

    Uses ``BlobServiceClient.from_connection_string`` per Microsoft quickstart:
    https://learn.microsoft.com/en-us/azure/storage/blobs/storage-quickstart-blobs-python
    """

    def __init__(
        self,
        connection_string: str,
        container_name: str,
        key_prefix: str = "",
    ) -> None:
        """Initialize blob client settings; container is created lazily on first use.

        Args:
            connection_string: Azure Storage connection string (Azurite or prod).
            container_name: Blob container name (e.g. ``cvs``).
            key_prefix: Optional prefix prepended to all logical keys.
        """
        normalized_prefix = key_prefix.strip("/")
        self._key_prefix = f"{normalized_prefix}/" if normalized_prefix else ""
        self._container_name = container_name
        self._connection_string = connection_string
        self._service_client: BlobServiceClient | None = None
        self._container_client = None
        self._container_ready = False

    def _ensure_container(self) -> None:
        """Create the blob service client and container on first use."""
        if self._container_ready:
            return
        self._service_client = BlobServiceClient.from_connection_string(self._connection_string)
        self._container_client = self._service_client.get_container_client(self._container_name)
        if not self._container_client.exists():
            self._container_client.create_container()
        self._container_ready = True

    def _storage_key(self, key: str) -> str:
        """Return the blob name for a logical key.

        Args:
            key: Caller-supplied logical key.

        Returns:
            str: Prefix-scoped blob name within the container.
        """
        logical_key = validate_blob_logical_key(key)
        return f"{self._key_prefix}{logical_key}"

    def _blob_client(self, key: str):
        """Return a BlobClient for the logical key."""
        assert self._container_client is not None
        return self._container_client.get_blob_client(self._storage_key(key))

    def put(self, key: str, data: bytes) -> None:
        """Upload bytes to blob storage, overwriting any existing blob."""
        self._ensure_container()
        self._blob_client(key).upload_blob(data, overwrite=True)

    def get(self, key: str) -> bytes:
        """Download blob bytes or raise when the blob is missing."""
        self._ensure_container()
        try:
            return self._blob_client(key).download_blob().readall()
        except ResourceNotFoundError as error:
            raise BlobNotFoundError(f"Blob not found: {key}") from error

    def delete(self, key: str) -> None:
        """Delete the blob or raise when the blob is missing."""
        self._ensure_container()
        try:
            self._blob_client(key).delete_blob()
        except ResourceNotFoundError as error:
            raise BlobNotFoundError(f"Blob not found: {key}") from error
