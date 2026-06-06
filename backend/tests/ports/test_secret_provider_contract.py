"""Contract tests for SecretProvider port implementations."""

import pytest

from app.ports.secret_provider import SecretNotFoundError, SecretProvider


def test_get_returns_configured_secret(secret_provider: SecretProvider, monkeypatch: pytest.MonkeyPatch) -> None:
    """SecretProvider.get returns the string value for a configured secret name."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

    assert secret_provider.get("OPENAI_API_KEY") == "sk-test-key"


def test_get_raises_when_secret_missing(secret_provider: SecretProvider, monkeypatch: pytest.MonkeyPatch) -> None:
    """SecretProvider.get raises SecretNotFoundError when the secret is not configured."""
    monkeypatch.delenv("MISSING_SECRET", raising=False)

    with pytest.raises(SecretNotFoundError):
        secret_provider.get("MISSING_SECRET")
