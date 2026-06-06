"""Application configuration loaded from environment variables."""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the API and worker processes."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://jobmatcher:jobmatcher@localhost:5432/jobmatcher"
    app_env: str = "development"
    allowed_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        description="Comma-separated browser origins permitted for CORS with credentials.",
    )

    blob_store_backend: str = Field(
        default="memory",
        description="BlobStore adapter: memory (CI/local pytest) or azurite (Docker Compose).",
    )
    azure_storage_connection_string: str | None = Field(
        default=None,
        description="Azure Storage connection string for Azurite or production Blob Storage.",
    )
    blob_container_name: str = Field(
        default="cvs",
        description="Blob container for CV PDF objects.",
    )
    blob_key_prefix: str = Field(
        default="cvs/",
        description="Logical key prefix enforced by BlobStore adapters.",
    )

    job_queue_backend: str = Field(
        default="in_process",
        description="JobQueue adapter: in_process (CI/local pytest) or rabbitmq (Docker Compose).",
    )
    rabbitmq_url: str | None = Field(
        default=None,
        description="AMQP broker URL when job_queue_backend is rabbitmq.",
    )
    job_queue_name: str = Field(
        default="analysis-runs",
        description="Durable queue name for Analysis Run dispatch messages.",
    )

    secret_provider_backend: str = Field(
        default="env",
        description="SecretProvider adapter: env reads process environment variables.",
    )

    @field_validator("allowed_origins")
    @classmethod
    def strip_origin_entries(cls, value: str) -> str:
        """Normalize comma-separated origin entries by trimming whitespace.

        Args:
            value: Raw ALLOWED_ORIGINS environment string.

        Returns:
            str: Cleaned comma-separated origins.
        """
        origins = [origin.strip() for origin in value.split(",") if origin.strip()]
        return ",".join(origins)

    @property
    def is_production(self) -> bool:
        """Return True when running in the production environment."""
        return self.app_env.lower() == "production"

    @property
    def cors_origins(self) -> list[str]:
        """Return parsed CORS origins for middleware configuration."""
        if not self.allowed_origins:
            return []
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


def get_settings() -> Settings:
    """Return application settings resolved from the environment.

    Returns:
        Settings: Parsed configuration values for the current process.
    """
    return Settings()
