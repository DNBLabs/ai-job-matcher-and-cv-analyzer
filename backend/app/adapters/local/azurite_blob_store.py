"""Azurite/connection-string BlobStore adapter for local Docker Compose development."""

from azure.storage.blob import BlobServiceClient

from app.adapters.blob_store_base import BlobServiceBlobStore


class AzuriteBlobStore(BlobServiceBlobStore):
    """BlobStore backed by the Azurite emulator via a connection string.

    Shares put/get/delete semantics with the production AzureBlobStore through
    ``BlobServiceBlobStore``; only client construction differs (connection string
    here vs. Managed Identity in prod). See Microsoft quickstart:
    https://learn.microsoft.com/en-us/azure/storage/blobs/storage-quickstart-blobs-python
    """

    def __init__(
        self,
        connection_string: str,
        container_name: str,
        key_prefix: str = "",
    ) -> None:
        """Configure connection string, container, and key prefix.

        Args:
            connection_string: Azurite (or Azure Storage) connection string.
            container_name: Blob container name (e.g. ``cvs``).
            key_prefix: Optional prefix prepended to all logical keys.
        """
        self._connection_string = connection_string
        super().__init__(container_name=container_name, key_prefix=key_prefix)

    def _build_service_client(self) -> BlobServiceClient:
        """Construct a BlobServiceClient from the configured connection string."""
        return BlobServiceClient.from_connection_string(self._connection_string)
