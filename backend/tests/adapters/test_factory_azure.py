"""Factory wiring tests for the production Azure backends (Task 27)."""

import pytest

from app.adapters.azure.blob_store import AzureBlobStore
from app.adapters.azure.graph_notification import GraphApiNotificationPort
from app.adapters.azure.key_vault_secret_provider import KeyVaultSecretProvider
from app.adapters.azure.service_bus_queue import ServiceBusJobQueue
from app.adapters.factory import (
    create_blob_store,
    create_job_queue,
    create_notification_port,
    create_secret_provider,
)
from app.adapters.local.log_notification import LogNotificationPort
from app.config import Settings


class _NullSecretProvider:
    def get(self, name: str) -> str:  # pragma: no cover - not called by graph backend
        raise AssertionError("graph backend must not read secrets")


def test_factory_creates_azure_blob_store_when_configured() -> None:
    settings = Settings(
        blob_store_backend="azure",
        blob_account_url="https://acct.blob.core.windows.net",
        azure_client_id="mi-client-id",
    )
    assert isinstance(create_blob_store(settings), AzureBlobStore)


def test_factory_azure_blob_requires_account_url() -> None:
    settings = Settings(blob_store_backend="azure", blob_account_url=None)
    with pytest.raises(ValueError, match="BLOB_ACCOUNT_URL"):
        create_blob_store(settings)


def test_factory_creates_service_bus_queue_when_configured() -> None:
    settings = Settings(
        job_queue_backend="servicebus",
        servicebus_namespace="ns.servicebus.windows.net",
    )
    assert isinstance(create_job_queue(settings), ServiceBusJobQueue)


def test_factory_service_bus_requires_namespace() -> None:
    settings = Settings(job_queue_backend="servicebus", servicebus_namespace=None)
    with pytest.raises(ValueError, match="SERVICEBUS_NAMESPACE"):
        create_job_queue(settings)


def test_factory_creates_key_vault_provider_when_configured() -> None:
    settings = Settings(
        secret_provider_backend="keyvault",
        key_vault_uri="https://kv.vault.azure.net/",
    )
    assert isinstance(create_secret_provider(settings), KeyVaultSecretProvider)


def test_factory_key_vault_requires_uri() -> None:
    settings = Settings(secret_provider_backend="keyvault", key_vault_uri=None)
    with pytest.raises(ValueError, match="KEY_VAULT_URI"):
        create_secret_provider(settings)


def test_factory_notification_log_default() -> None:
    port = create_notification_port(Settings(notification_backend="log"), _NullSecretProvider())
    assert isinstance(port, LogNotificationPort)


def test_factory_creates_graph_notification_without_secret_provider() -> None:
    settings = Settings(notification_backend="graph", email_from="noreply@dnblabs.co.uk")
    port = create_notification_port(settings, _NullSecretProvider())
    assert isinstance(port, GraphApiNotificationPort)


def test_factory_rejects_unknown_notification_backend() -> None:
    with pytest.raises(ValueError):
        create_notification_port(Settings(notification_backend="carrier-pigeon"), _NullSecretProvider())
