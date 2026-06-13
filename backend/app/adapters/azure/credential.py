"""Shared Managed Identity credential factory for the Azure production adapters.

All Azure adapters authenticate with the Container App's user-assigned Managed
Identity — no secrets are stored in the image or Terraform state
(CONTEXT §Secrets). ``DefaultAzureCredential`` resolves that identity at runtime;
the user-assigned MI's client id is passed explicitly so the credential targets
the right identity when more than one is available.

Source: https://learn.microsoft.com/en-us/python/api/overview/azure/identity-readme#defaultazurecredential
"""

from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential


def create_azure_credential(client_id: str | None = None) -> TokenCredential:
    """Return a Managed Identity credential for the Azure adapters.

    Args:
        client_id: User-assigned Managed Identity client id (``AZURE_CLIENT_ID``).
            When omitted, the ambient system-assigned identity / environment is used.

    Returns:
        TokenCredential: A credential backed by the Container App Managed Identity.
    """
    if client_id:
        return DefaultAzureCredential(managed_identity_client_id=client_id)
    return DefaultAzureCredential()
