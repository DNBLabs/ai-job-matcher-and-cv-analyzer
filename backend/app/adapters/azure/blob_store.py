"""Production Azure Blob Storage adapter authenticated by Managed Identity.

Unlike the local Azurite adapter (connection-string auth), production access uses
the Container App Managed Identity over the account's blob endpoint — Blob public
access is disabled and only the MI may read/write (CONTEXT §Network; THREAT_MODEL
R3). The API MI has read/write on the ``cvs`` container; the Worker MI is
read-only (infra/app/identity.tf).

Source: https://learn.microsoft.com/en-us/azure/storage/blobs/storage-quickstart-blobs-python#authenticate-to-azure-and-authorize-access-to-blob-data
    BlobServiceClient(account_url, credential=DefaultAzureCredential())
"""

from azure.core.credentials import TokenCredential
from azure.storage.blob import BlobServiceClient

from app.adapters.blob_store_base import BlobServiceBlobStore


class AzureBlobStore(BlobServiceBlobStore):
    """BlobStore backed by Azure Blob Storage using a Managed Identity credential."""

    def __init__(
        self,
        *,
        account_url: str | None = None,
        credential: TokenCredential | None = None,
        container_name: str,
        key_prefix: str = "",
        service_client: BlobServiceClient | None = None,
    ) -> None:
        """Bind to a storage account; build the client from MI unless one is injected.

        Args:
            account_url: Blob endpoint (``https://<account>.blob.core.windows.net``).
                Required unless ``service_client`` is supplied.
            credential: Managed Identity credential. Required unless ``service_client``
                is supplied.
            container_name: Blob container name (e.g. ``cvs``).
            key_prefix: Logical key prefix enforced on all operations.
            service_client: Pre-built BlobServiceClient-like object (used in tests).

        Raises:
            ValueError: When neither a service_client nor account_url + credential is given.
        """
        if service_client is None and (not account_url or credential is None):
            raise ValueError("AzureBlobStore requires account_url and credential")
        self._account_url = account_url
        self._credential = credential
        super().__init__(
            container_name=container_name,
            key_prefix=key_prefix,
            service_client=service_client,
        )

    def _build_service_client(self) -> BlobServiceClient:
        """Construct a BlobServiceClient bound to the Managed Identity credential."""
        return BlobServiceClient(account_url=self._account_url, credential=self._credential)
