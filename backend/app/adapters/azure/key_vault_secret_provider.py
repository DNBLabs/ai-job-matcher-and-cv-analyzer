"""Azure Key Vault SecretProvider adapter (production, Managed Identity).

Reads secret values directly from Key Vault using the Container App Managed
Identity (CONTEXT §Secrets: "Production secrets in Azure Key Vault only; loaded
via Managed Identity at runtime"). The MI is granted per-secret ``Key Vault
Secrets User`` so the API cannot read the worker's secrets and vice versa
(infra/app/identity.tf; THREAT_MODEL R3/R4).

Logical names use the env-var convention (``OPENAI_API_KEY``) shared with the
local EnvSecretProvider; Key Vault names are kebab-case (``openai-api-key``), so
the adapter maps between them deterministically.

Source: https://learn.microsoft.com/en-us/python/api/overview/azure/keyvault-secrets-readme
    SecretClient(vault_url=..., credential=...).get_secret(name).value
"""

from typing import Protocol

from azure.core.credentials import TokenCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.keyvault.secrets import SecretClient

from app.adapters.boundary_validation import validate_secret_name
from app.ports.secret_provider import SecretNotFoundError


class _SecretReader(Protocol):
    """Minimal surface of azure.keyvault.secrets.SecretClient used here."""

    def get_secret(self, name: str): ...  # noqa: ANN201 — returns KeyVaultSecret


def _to_key_vault_name(logical_name: str) -> str:
    """Map an env-style secret name to its Key Vault kebab-case equivalent.

    Args:
        logical_name: Validated env-var-style name (e.g. ``OPENAI_API_KEY``).

    Returns:
        str: Key Vault secret name (e.g. ``openai-api-key``).
    """
    return logical_name.lower().replace("_", "-")


class KeyVaultSecretProvider:
    """Resolve secrets from Azure Key Vault via the Container App Managed Identity."""

    def __init__(
        self,
        *,
        vault_url: str | None = None,
        credential: TokenCredential | None = None,
        client: _SecretReader | None = None,
    ) -> None:
        """Bind the adapter to a Key Vault, building a SecretClient when not injected.

        Args:
            vault_url: Key Vault URI (``https://<vault>.vault.azure.net/``). Required
                unless ``client`` is supplied.
            credential: Managed Identity credential. Required unless ``client`` is supplied.
            client: Pre-built SecretClient-like object (used in tests).

        Raises:
            ValueError: When neither a client nor a vault_url + credential is given.
        """
        if client is not None:
            self._client = client
        else:
            if not vault_url or credential is None:
                raise ValueError("KeyVaultSecretProvider requires vault_url and credential")
            self._client = SecretClient(vault_url=vault_url, credential=credential)

    def get(self, name: str) -> str:
        """Return the secret value for an env-style logical name.

        Args:
            name: Env-var-style secret identifier (e.g. ``OPENAI_API_KEY``).

        Returns:
            str: Secret value resolved from Key Vault.

        Raises:
            InvalidSecretNameError: When the name is not a safe identifier.
            SecretNotFoundError: When the secret is absent from the vault.
        """
        validated = validate_secret_name(name)
        kv_name = _to_key_vault_name(validated)
        try:
            return self._client.get_secret(kv_name).value
        except ResourceNotFoundError as error:
            raise SecretNotFoundError(f"Secret not found: {kv_name}") from error
