"""Resend NotificationPort adapter for production transactional email.

Renders provider-agnostic templates and delivers them via the Resend HTTP API.
The API key is resolved through the SecretProvider port (never hard-coded) and
sent as a bearer token (CONTEXT §3 "Production secrets in Azure Key Vault only").

Source: https://resend.com/docs/api-reference/emails/send-email
    POST https://api.resend.com/emails
    Authorization: Bearer <api_key>
    Content-Type: application/json
    body: { from, to: [..], subject, html, text }
"""

import httpx

from app.notifications.templates import (
    EmailContent,
    render_magic_link_email,
    render_run_complete_email,
)

_RESEND_BASE_URL = "https://api.resend.com"
_SEND_TIMEOUT_SECONDS = 10.0


class NotificationDeliveryError(Exception):
    """Raised when the Resend provider rejects or fails to accept a message."""


class ResendNotificationPort:
    """Deliver transactional emails via the Resend HTTP API."""

    def __init__(
        self,
        *,
        api_key: str,
        from_email: str,
        base_url: str = _RESEND_BASE_URL,
        client: httpx.Client | None = None,
    ) -> None:
        """Bind the adapter to Resend credentials and an optional HTTP client.

        Args:
            api_key: Resend API key resolved from the SecretProvider port.
            from_email: Verified sender, e.g. ``AI Job Matcher <no-reply@domain>``.
            base_url: Resend API origin (overridable for tests).
            client: Optional injected HTTP client; a short-lived client is created
                per send when omitted.
        """
        self._api_key = api_key
        self._from_email = from_email
        self._base_url = base_url.rstrip("/")
        self._client = client

    def send_magic_link_email(self, *, to_email: str, verify_url: str) -> None:
        """Deliver the passwordless sign-in email via Resend.

        Args:
            to_email: Normalized recipient email address.
            verify_url: Absolute single-use verification URL.

        Raises:
            NotificationDeliveryError: When the provider call fails.
        """
        self._send(to_email=to_email, content=render_magic_link_email(verify_url=verify_url))

    def send_run_complete_email(self, *, to_email: str, results_url: str) -> None:
        """Deliver the run-completion email via Resend.

        Args:
            to_email: Run owner's email address.
            results_url: Absolute results deep link (no share token).

        Raises:
            NotificationDeliveryError: When the provider call fails.
        """
        self._send(to_email=to_email, content=render_run_complete_email(results_url=results_url))

    def _send(self, *, to_email: str, content: EmailContent) -> None:
        """POST a rendered email to the Resend ``/emails`` endpoint.

        Args:
            to_email: Recipient email address.
            content: Rendered subject, HTML, and text bodies.

        Raises:
            NotificationDeliveryError: When the request errors or returns non-2xx.
        """
        payload = {
            "from": self._from_email,
            "to": [to_email],
            "subject": content.subject,
            "html": content.html,
            "text": content.text,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self._base_url}/emails"

        client = self._client or httpx.Client(timeout=_SEND_TIMEOUT_SECONDS)
        try:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
        except Exception as error:  # noqa: BLE001 — normalize all delivery failures
            raise NotificationDeliveryError("failed to send email via Resend") from error
        finally:
            if self._client is None:
                client.close()
