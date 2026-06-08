"""Factory functions wiring infrastructure ports from application settings."""

from app.adapters.local.azurite_blob_store import AzuriteBlobStore
from app.adapters.local.env_secret_provider import EnvSecretProvider
from app.adapters.local.in_process_job_queue import InProcessJobQueue
from app.adapters.local.log_notification import LogNotificationPort
from app.adapters.local.memory_blob_store import MemoryBlobStore
from app.adapters.local.rabbitmq_job_queue import RabbitMQJobQueue
from app.adapters.openai_client import OpenAiLlmClient
from app.config import Settings
from app.ports.blob_store import BlobStore
from app.ports.job_queue import JobQueue
from app.ports.llm_client import LlmClient
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
    raise ValueError(f"Unsupported job queue backend: {settings.job_queue_backend}")


def create_notification_port(settings: Settings) -> NotificationPort:
    """Return a NotificationPort adapter for the configured backend.

    Args:
        settings: Application settings describing notification wiring.

    Returns:
        NotificationPort: Log-backed implementation for local development.
    """
    _ = settings
    return LogNotificationPort()


def create_secret_provider(settings: Settings) -> SecretProvider:
    """Return a SecretProvider adapter for the configured backend.

    Args:
        settings: Application settings describing secret resolution wiring.

    Returns:
        SecretProvider: Environment-backed implementation for local development.
    """
    if settings.secret_provider_backend == "env":
        return EnvSecretProvider()
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
    return OpenAiLlmClient(api_key=api_key, model=settings.openai_title_model)
