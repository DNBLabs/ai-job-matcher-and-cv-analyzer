"""Tests for the Microsoft Graph sendMail NotificationPort adapter (Task 27).

Uses a fake Managed Identity credential and a fake HTTP client so the request
(endpoint, bearer auth, Graph message body) is asserted without a live token or
network call. Decision of record: CONTEXT 2026-06-11 (Graph replaces Resend).
"""

import pytest

from app.adapters.azure.graph_notification import (
    GraphApiNotificationPort,
    NotificationDeliveryError,
)


class _FakeAccessToken:
    def __init__(self, token: str) -> None:
        self.token = token


class _FakeCredential:
    def __init__(self) -> None:
        self.scopes: list = []

    def get_token(self, *scopes: str) -> _FakeAccessToken:
        self.scopes.append(scopes)
        return _FakeAccessToken("graph-token-xyz")


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _FakeHttpClient:
    def __init__(self, *, status_code: int = 202) -> None:
        self.status_code = status_code
        self.calls: list[dict] = []

    def post(self, url: str, *, headers: dict, json: dict) -> _FakeResponse:
        self.calls.append({"url": url, "headers": headers, "json": json})
        return _FakeResponse(self.status_code)


def _adapter(client: _FakeHttpClient) -> GraphApiNotificationPort:
    return GraphApiNotificationPort(
        mailbox="noreply@dnblabs.co.uk",
        credential=_FakeCredential(),
        client=client,
    )


def test_magic_link_posts_to_shared_mailbox_sendmail_with_bearer() -> None:
    """sendMail targets the shared mailbox endpoint with the MI bearer token."""
    client = _FakeHttpClient()
    _adapter(client).send_magic_link_email(
        to_email="alex@example.com",
        verify_url="https://api.example.com/auth/magic-link/verify?token=abc",
    )

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["url"] == (
        "https://graph.microsoft.com/v1.0/users/noreply@dnblabs.co.uk/sendMail"
    )
    assert call["headers"]["Authorization"] == "Bearer graph-token-xyz"
    assert call["headers"]["Content-Type"] == "application/json"


def test_message_body_matches_graph_sendmail_schema() -> None:
    """The body carries the Graph message schema with HTML content and recipient."""
    client = _FakeHttpClient()
    verify_url = "https://api.example.com/auth/magic-link/verify?token=abc"
    _adapter(client).send_magic_link_email(to_email="alex@example.com", verify_url=verify_url)

    body = client.calls[0]["json"]
    message = body["message"]
    assert message["subject"] == "Sign in to AI Job Matcher"
    assert message["body"]["contentType"] == "HTML"
    assert verify_url in message["body"]["content"]
    assert message["toRecipients"] == [{"emailAddress": {"address": "alex@example.com"}}]
    assert body["saveToSentItems"] is False


def test_run_complete_email_carries_results_deep_link() -> None:
    """The run-completion email body carries the results deep link."""
    client = _FakeHttpClient()
    results_url = "https://app.example.com/runs/abc"
    _adapter(client).send_run_complete_email(to_email="alex@example.com", results_url=results_url)

    message = client.calls[0]["json"]["message"]
    assert message["subject"] == "Your job matches are ready"
    assert results_url in message["body"]["content"]


def test_token_requested_for_graph_default_scope() -> None:
    """The adapter requests a token for the Microsoft Graph .default scope."""
    client = _FakeHttpClient()
    credential = _FakeCredential()
    GraphApiNotificationPort(
        mailbox="noreply@dnblabs.co.uk", credential=credential, client=client
    ).send_run_complete_email(to_email="a@b.com", results_url="https://x/runs/1")

    assert credential.scopes == [("https://graph.microsoft.com/.default",)]


def test_non_202_response_raises_delivery_error() -> None:
    """A non-202 Graph response surfaces as NotificationDeliveryError."""
    client = _FakeHttpClient(status_code=403)
    with pytest.raises(NotificationDeliveryError):
        _adapter(client).send_magic_link_email(
            to_email="alex@example.com", verify_url="https://x/verify?token=abc"
        )
