"""Tests for the Resend NotificationPort adapter and factory wiring (Task 19).

The adapter is exercised with an injected fake HTTP client so the request shape
(endpoint, bearer auth, JSON body) is asserted without any live network call.
"""

import pytest

from app.adapters.factory import create_notification_port
from app.adapters.local.log_notification import LogNotificationPort
from app.adapters.resend_notification import (
    NotificationDeliveryError,
    ResendNotificationPort,
)
from app.config import Settings


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeHttpClient:
    """Captures the last POST instead of performing a network request."""

    def __init__(self, *, status_code: int = 200) -> None:
        self.status_code = status_code
        self.calls: list[dict] = []

    def post(self, url: str, *, headers: dict, json: dict) -> _FakeResponse:
        self.calls.append({"url": url, "headers": headers, "json": json})
        return _FakeResponse(self.status_code)


class _RecordingSecretProvider:
    """Returns a fixed secret and records every requested name."""

    def __init__(self, value: str) -> None:
        self._value = value
        self.requested: list[str] = []

    def get(self, name: str) -> str:
        self.requested.append(name)
        return self._value


def _adapter(client: _FakeHttpClient) -> ResendNotificationPort:
    return ResendNotificationPort(
        api_key="re_test_key",
        from_email="AI Job Matcher <no-reply@example.com>",
        client=client,
    )


def test_magic_link_posts_to_resend_emails_endpoint_with_bearer_auth() -> None:
    """Sending a magic link POSTs to /emails with the API key as a bearer token."""
    client = _FakeHttpClient()
    _adapter(client).send_magic_link_email(
        to_email="alex@example.com",
        verify_url="https://api.example.com/auth/magic-link/verify?token=abc",
    )

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["url"] == "https://api.resend.com/emails"
    assert call["headers"]["Authorization"] == "Bearer re_test_key"
    assert call["headers"]["Content-Type"] == "application/json"


def test_magic_link_body_carries_recipient_subject_and_rendered_bodies() -> None:
    """The JSON body includes from, to, subject, and both HTML and text bodies."""
    client = _FakeHttpClient()
    verify_url = "https://api.example.com/auth/magic-link/verify?token=abc"
    _adapter(client).send_magic_link_email(to_email="alex@example.com", verify_url=verify_url)

    body = client.calls[0]["json"]
    assert body["from"] == "AI Job Matcher <no-reply@example.com>"
    assert body["to"] == ["alex@example.com"]
    assert body["subject"] == "Sign in to AI Job Matcher"
    assert verify_url in body["html"]
    assert verify_url in body["text"]


def test_run_complete_body_carries_results_deep_link() -> None:
    """The run-completion email body carries the results deep link."""
    client = _FakeHttpClient()
    results_url = "https://app.example.com/runs/abc"
    _adapter(client).send_run_complete_email(to_email="alex@example.com", results_url=results_url)

    body = client.calls[0]["json"]
    assert body["subject"] == "Your job matches are ready"
    assert results_url in body["html"]
    assert results_url in body["text"]


def test_non_2xx_response_raises_delivery_error() -> None:
    """A 4xx/5xx provider response surfaces as a NotificationDeliveryError."""
    client = _FakeHttpClient(status_code=422)
    with pytest.raises(NotificationDeliveryError):
        _adapter(client).send_magic_link_email(
            to_email="alex@example.com",
            verify_url="https://api.example.com/verify?token=abc",
        )


def test_factory_returns_log_adapter_by_default() -> None:
    """The default notification backend resolves to the local log adapter."""
    settings = Settings(notification_backend="log")
    secret_provider = _RecordingSecretProvider("unused")

    port = create_notification_port(settings, secret_provider)

    assert isinstance(port, LogNotificationPort)
    assert secret_provider.requested == []


def test_factory_resend_backend_loads_api_key_via_secret_provider() -> None:
    """The resend backend resolves RESEND_API_KEY through the SecretProvider port."""
    settings = Settings(
        notification_backend="resend",
        email_from="AI Job Matcher <no-reply@example.com>",
    )
    secret_provider = _RecordingSecretProvider("re_live_key")

    port = create_notification_port(settings, secret_provider)

    assert isinstance(port, ResendNotificationPort)
    assert secret_provider.requested == ["RESEND_API_KEY"]


def test_factory_rejects_unknown_backend() -> None:
    """An unsupported notification backend is a configuration error."""
    settings = Settings(notification_backend="carrier-pigeon")
    with pytest.raises(ValueError):
        create_notification_port(settings, _RecordingSecretProvider("x"))
