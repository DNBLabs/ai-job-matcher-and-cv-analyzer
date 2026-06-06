"""Tests for infrastructure adapter factory wiring."""

import pytest

from app.adapters.factory import create_blob_store, create_job_queue, create_secret_provider
from app.adapters.local.azurite_blob_store import AzuriteBlobStore
from app.adapters.local.env_secret_provider import EnvSecretProvider
from app.adapters.local.in_process_job_queue import InProcessJobQueue
from app.adapters.local.memory_blob_store import MemoryBlobStore
from app.adapters.local.rabbitmq_job_queue import RabbitMQJobQueue
from app.config import Settings


def test_factory_creates_memory_blob_store_by_default() -> None:
    """Default settings use the in-memory BlobStore for CI and local pytest."""
    blob_store = create_blob_store(Settings())

    assert isinstance(blob_store, MemoryBlobStore)


def test_factory_creates_in_process_job_queue_by_default() -> None:
    """Default settings use the in-process JobQueue for CI and local pytest."""
    job_queue = create_job_queue(Settings())

    assert isinstance(job_queue, InProcessJobQueue)


def test_factory_creates_env_secret_provider_by_default() -> None:
    """Default settings use environment variables for SecretProvider."""
    secret_provider = create_secret_provider(Settings())

    assert isinstance(secret_provider, EnvSecretProvider)


def test_factory_creates_azurite_blob_store_when_configured() -> None:
    """Azurite backend is selected when connection string settings are present."""
    settings = Settings(
        blob_store_backend="azurite",
        azure_storage_connection_string=(
            "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;"
            "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
            "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
        ),
    )

    blob_store = create_blob_store(settings)

    assert isinstance(blob_store, AzuriteBlobStore)


def test_factory_creates_rabbitmq_job_queue_when_configured() -> None:
    """RabbitMQ backend is selected when broker URL settings are present."""
    settings = Settings(
        job_queue_backend="rabbitmq",
        rabbitmq_url="amqp://jobmatcher:jobmatcher@localhost:5672/",
    )

    job_queue = create_job_queue(settings)

    assert isinstance(job_queue, RabbitMQJobQueue)


def test_factory_raises_when_azurite_selected_without_connection_string() -> None:
    """Azurite backend requires AZURE_STORAGE_CONNECTION_STRING."""
    settings = Settings(blob_store_backend="azurite", azure_storage_connection_string=None)

    with pytest.raises(ValueError, match="AZURE_STORAGE_CONNECTION_STRING"):
        create_blob_store(settings)
