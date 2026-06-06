"""SecretProvider port for loading runtime secrets without cloud SDK coupling."""

from typing import Protocol


class SecretNotFoundError(LookupError):
    """Raised when a requested secret name is not available."""


class InvalidSecretNameError(ValueError):
    """Raised when a secret name fails boundary validation."""


class SecretProvider(Protocol):
    """Port for resolving secret values by name from the configured backend."""

    def get(self, name: str) -> str:
        """Return the secret value for the given name.

        Args:
            name: Environment-style secret identifier (e.g. ``OPENAI_API_KEY``).

        Returns:
            str: Plain-text secret value.

        Raises:
            SecretNotFoundError: When the secret is missing or empty.
            InvalidSecretNameError: When the secret name fails boundary validation.
        """
        ...
