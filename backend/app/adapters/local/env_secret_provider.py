"""Environment-variable SecretProvider adapter for local Docker Compose development."""

import os

from app.adapters.boundary_validation import validate_secret_name
from app.ports.secret_provider import SecretNotFoundError


class EnvSecretProvider:
    """Load secrets from process environment variables (local ``.env`` / Compose)."""

    def get(self, name: str) -> str:
        """Return the secret value from ``os.environ``.

        Args:
            name: Environment variable name holding the secret.

        Returns:
            str: Non-empty secret value.

        Raises:
            SecretNotFoundError: When the variable is unset or blank.
        """
        validated_name = validate_secret_name(name)
        value = os.environ.get(validated_name)
        if value is None or value == "":
            raise SecretNotFoundError(f"Secret not found: {validated_name}")
        return value
