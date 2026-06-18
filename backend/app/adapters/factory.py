"""Factory functions wiring infrastructure ports from application settings."""

from app.adapters.azure.blob_store import AzureBlobStore
from app.adapters.azure.credential import create_azure_credential
from app.adapters.azure.graph_notification import GraphApiNotificationPort
from app.adapters.azure.key_vault_secret_provider import KeyVaultSecretProvider
from app.adapters.azure.service_bus_queue import ServiceBusJobQueue
from app.adapters.local.azurite_blob_store import AzuriteBlobStore
from app.adapters.local.env_secret_provider import EnvSecretProvider
from app.adapters.local.in_process_job_queue import InProcessJobQueue
from app.adapters.local.log_notification import LogNotificationPort
from app.adapters.local.memory_blob_store import MemoryBlobStore
from app.adapters.local.rabbitmq_job_queue import RabbitMQJobQueue
from app.adapters.openai_client import OpenAiLlmClient
from app.config import Settings
from app.job_sources.adzuna import AdzunaJobSource
from app.job_sources.base import JobSource
from app.job_sources.reed import ReedJobSource
from app.ports.blob_store import BlobStore
from app.ports.job_queue import JobQueue
from app.ports.llm_client import LlmClient, ScoringLlmClient
from app.ports.notification import NotificationPort
from app.ports.secret_provider import SecretNotFoundError, SecretProvider


def create_blob_store(settings: Settings) -> BlobStore:
    """Return a BlobStore adapter for the configured backend.

    Args:
        settings: Application settings describing blob storage wiring.

    Returns:
        BlobStore: Memory or Azurite-backed implementation.

    Raises:
        ValueError: When Azurite backend is selected without a connection string.
    """
    if settings.blob_store_backend == "memory":
        return MemoryBlobStore(key_prefix=settings.blob_key_prefix)
    if settings.blob_store_backend == "azurite":
        if not settings.azure_storage_connection_string:
            raise ValueError("AZURE_STORAGE_CONNECTION_STRING is required for azurite blob backend")
        return AzuriteBlobStore(
            connection_string=settings.azure_storage_connection_string,
            container_name=settings.blob_container_name,
            key_prefix=settings.blob_key_prefix,
        )
    if settings.blob_store_backend == "azure":
        if not settings.blob_account_url:
            raise ValueError("BLOB_ACCOUNT_URL is required for the azure blob backend")
        return AzureBlobStore(
            account_url=settings.blob_account_url,
            credential=create_azure_credential(settings.azure_client_id),
            container_name=settings.blob_container_name,
            key_prefix=settings.blob_key_prefix,
        )
    raise ValueError(f"Unsupported blob store backend: {settings.blob_store_backend}")


def create_job_queue(settings: Settings) -> JobQueue:
    """Return a JobQueue adapter for the configured backend.

    Args:
        settings: Application settings describing queue wiring.

    Returns:
        JobQueue: In-process or RabbitMQ-backed implementation.

    Raises:
        ValueError: When RabbitMQ backend is selected without a broker URL.
    """
    if settings.job_queue_backend == "in_process":
        return InProcessJobQueue()
    if settings.job_queue_backend == "rabbitmq":
        if not settings.rabbitmq_url:
            raise ValueError("RABBITMQ_URL is required for rabbitmq job queue backend")
        return RabbitMQJobQueue(
            rabbitmq_url=settings.rabbitmq_url,
            queue_name=settings.job_queue_name,
        )
    if settings.job_queue_backend == "servicebus":
        if not settings.servicebus_namespace:
            raise ValueError("SERVICEBUS_NAMESPACE is required for the servicebus job queue backend")
        return ServiceBusJobQueue(
            queue_name=settings.job_queue_name,
            fully_qualified_namespace=settings.servicebus_namespace,
            credential=create_azure_credential(settings.azure_client_id),
        )
    raise ValueError(f"Unsupported job queue backend: {settings.job_queue_backend}")


def create_notification_port(
    settings: Settings, secret_provider: SecretProvider
) -> NotificationPort:
    """Return a NotificationPort adapter for the configured backend.

    Args:
        settings: Application settings describing notification wiring.
        secret_provider: Unused by the graph backend (Managed Identity, no stored key);
            kept for interface symmetry with the other factory functions.

    Returns:
        NotificationPort: Log-backed (local) or Graph-backed (production) adapter.

    Raises:
        ValueError: When the configured notification backend is unsupported.
    """
    if settings.notification_backend == "log":
        return LogNotificationPort()
    if settings.notification_backend == "graph":
        return GraphApiNotificationPort(
            mailbox=settings.email_from,
            credential=create_azure_credential(settings.azure_client_id),
        )
    raise ValueError(f"Unsupported notification backend: {settings.notification_backend}")


def create_secret_provider(settings: Settings) -> SecretProvider:
    """Return a SecretProvider adapter for the configured backend.

    Args:
        settings: Application settings describing secret resolution wiring.

    Returns:
        SecretProvider: Environment-backed (local) or Key Vault-backed (production) adapter.

    Raises:
        ValueError: When the keyvault backend is selected without ``KEY_VAULT_URI``.
    """
    if settings.secret_provider_backend == "env":
        return EnvSecretProvider()
    if settings.secret_provider_backend == "keyvault":
        if not settings.key_vault_uri:
            raise ValueError("KEY_VAULT_URI is required for the keyvault secret provider backend")
        return KeyVaultSecretProvider(
            vault_url=settings.key_vault_uri,
            credential=create_azure_credential(settings.azure_client_id),
        )
    raise ValueError(f"Unsupported secret provider backend: {settings.secret_provider_backend}")


def create_llm_client(settings: Settings, secret_provider: SecretProvider) -> LlmClient:
    """Return an LlmClient adapter wired to OpenAI for title suggestions.

    Args:
        settings: Application settings describing the title suggestion model.
        secret_provider: SecretProvider port for resolving ``OPENAI_API_KEY``.

    Returns:
        LlmClient: OpenAI-backed structured completion client.

    Raises:
        SecretNotFoundError: When ``OPENAI_API_KEY`` is missing from the provider.
    """
    api_key = secret_provider.get("OPENAI_API_KEY")
    return OpenAiLlmClient(
        api_key=api_key,
        title_model=settings.openai_title_model,
        scoring_model=settings.openai_scoring_model,
    )


def create_scoring_llm_client(
    settings: Settings, secret_provider: SecretProvider
) -> ScoringLlmClient:
    """Return a ScoringLlmClient wired to OpenAI for per-listing Analysis Run scoring.

    Args:
        settings: Application settings describing the scoring model.
        secret_provider: SecretProvider port for resolving ``OPENAI_API_KEY``.

    Returns:
        ScoringLlmClient: OpenAI-backed structured scoring client.

    Raises:
        SecretNotFoundError: When ``OPENAI_API_KEY`` is missing from the provider.
    """
    api_key = secret_provider.get("OPENAI_API_KEY")
    return OpenAiLlmClient(
        api_key=api_key,
        title_model=settings.openai_title_model,
        scoring_model=settings.openai_scoring_model,
    )


def create_adzuna_job_source(secret_provider: SecretProvider) -> JobSource:
    """Return the Adzuna JobSource adapter wired with credentials from secrets.

    Args:
        secret_provider: SecretProvider port resolving ``ADZUNA_APP_ID`` and
            ``ADZUNA_APP_KEY`` (Worker Managed Identity scope in production).

    Returns:
        JobSource: Adzuna-backed adapter for UK listings.

    Raises:
        SecretNotFoundError: When an Adzuna credential is missing from the provider.
    """
    return AdzunaJobSource(
        app_id=secret_provider.get("ADZUNA_APP_ID"),
        app_key=secret_provider.get("ADZUNA_APP_KEY"),
    )


def create_reed_job_source(secret_provider: SecretProvider) -> JobSource:
    """Return the Reed JobSource adapter wired with the API key from secrets.

    Args:
        secret_provider: SecretProvider port resolving ``REED_API_KEY`` (Worker
            Managed Identity scope in production).

    Returns:
        JobSource: Reed-backed adapter for UK listings.

    Raises:
        SecretNotFoundError: When ``REED_API_KEY`` is missing from the provider.
    """
    return ReedJobSource(api_key=secret_provider.get("REED_API_KEY"))
