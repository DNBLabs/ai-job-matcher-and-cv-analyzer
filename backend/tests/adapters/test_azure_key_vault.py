"""Contract + security tests for the Azure Key Vault SecretProvider adapter.

A fake SecretClient stands in for ``azure.keyvault.secrets.SecretClient`` so the
name-mapping and error semantics are asserted without any live Key Vault call.
"""

import pytest
from azure.core.exceptions import ResourceNotFoundError

from app.adapters.azure.key_vault_secret_provider import KeyVaultSecretProvider
from app.ports.secret_provider import (
    InvalidSecretNameError,
    SecretNotFoundError,
)


class _FakeSecret:
    def __init__(self, value: str) -> None:
        self.value = value


class _FakeSecretClient:
    """Records requested Key Vault secret names and returns canned values."""

    def __init__(self, secrets: dict[str, str]) -> None:
        self._secrets = secrets
        self.requested: list[str] = []

    def get_secret(self, name: str) -> _FakeSecret:
        self.requested.append(name)
        try:
            return _FakeSecret(self._secrets[name])
        except KeyError as error:
            raise ResourceNotFoundError(f"missing: {name}") from error


def _provider(secrets: dict[str, str]) -> tuple[KeyVaultSecretProvider, _FakeSecretClient]:
    client = _FakeSecretClient(secrets)
    return KeyVaultSecretProvider(client=client), client


def test_get_returns_secret_value() -> None:
    """get returns the string value resolved from Key Vault."""
    provider, _ = _provider({"openai-api-key": "sk-live"})

    assert provider.get("OPENAI_API_KEY") == "sk-live"


def test_env_style_name_is_mapped_to_kebab_case_kv_name() -> None:
    """An env-style logical name is translated to the Key Vault kebab-case name."""
    provider, client = _provider({"google-oauth-client-secret": "shh"})

    provider.get("GOOGLE_OAUTH_CLIENT_SECRET")

    assert client.requested == ["google-oauth-client-secret"]


def test_missing_secret_raises_secret_not_found() -> None:
    """A Key Vault ResourceNotFoundError surfaces as the port's SecretNotFoundError."""
    provider, _ = _provider({})

    with pytest.raises(SecretNotFoundError):
        provider.get("ADZUNA_APP_ID")


def test_invalid_secret_name_rejected_at_boundary() -> None:
    """Names that are not safe env-var identifiers are rejected before any KV call."""
    provider, client = _provider({})

    with pytest.raises(InvalidSecretNameError):
        provider.get("not a valid name")

    assert client.requested == []
