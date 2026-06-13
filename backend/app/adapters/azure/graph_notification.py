"""Microsoft Graph sendMail NotificationPort adapter (production).

Sends transactional email from the M365 shared mailbox ``noreply@dnblabs.co.uk``
via ``POST /users/{mailbox}/sendMail``, authenticated by the Container App
Managed Identity — no API key is stored (CONTEXT decision 2026-06-11, replacing
Resend). The MI's ``Mail.Send`` *application* permission MUST be constrained to
only the shared mailbox by an Exchange Online Application Access Policy
(see docs/adr/0005 and docs/ops/RUNBOOK); unconstrained ``Mail.Send`` can send as
any tenant mailbox.

Renders the provider-agnostic templates (subject + HTML) and maps them onto the
Graph message schema.

Source: https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0
    POST https://graph.microsoft.com/v1.0/users/{mailbox}/sendMail
    Authorization: Bearer {token}; Content-Type: application/json
    body: { message: { subject, body: {contentType, content}, toRecipients }, saveToSentItems }
    success: 202 Accepted
"""

from azure.core.credentials import TokenCredential
import httpx

from app.notifications.templates import (
    EmailContent,
    render_magic_link_email,
    render_run_complete_email,
)

_GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
_GRAPH_SCOPE = "https://graph.microsoft.com/.default"
_SEND_TIMEOUT_SECONDS = 10.0
_ACCEPTED = 202


class NotificationDeliveryError(Exception):
    """Raised when Microsoft Graph rejects or fails to accept a message."""


class GraphApiNotificationPort:
    """Deliver transactional email via Microsoft Graph sendMail using Managed Identity."""

    def __init__(
        self,
        *,
        mailbox: str,
        credential: TokenCredential,
        base_url: str = _GRAPH_BASE_URL,
        client: httpx.Client | None = None,
    ) -> None:
        """Bind the adapter to a shared mailbox and Managed Identity credential.

        Args:
            mailbox: Shared mailbox address sent from and used in the sendMail URL
                (``noreply@dnblabs.co.uk``).
            credential: Managed Identity credential providing Graph access tokens.
            base_url: Graph API origin (overridable for tests).
            client: Optional injected HTTP client; a short-lived client is created
                per send when omitted.
        """
        self._mailbox = mailbox
        self._credential = credential
        self._base_url = base_url.rstrip("/")
        self._client = client

    def send_magic_link_email(self, *, to_email: str, verify_url: str) -> None:
        """Deliver the passwordless sign-in email via Graph.

        Raises:
            NotificationDeliveryError: When the Graph call fails.
        """
        self._send(to_email=to_email, content=render_magic_link_email(verify_url=verify_url))

    def send_run_complete_email(self, *, to_email: str, results_url: str) -> None:
        """Deliver the run-completion email via Graph.

        Raises:
            NotificationDeliveryError: When the Graph call fails.
        """
        self._send(to_email=to_email, content=render_run_complete_email(results_url=results_url))

    def _send(self, *, to_email: str, content: EmailContent) -> None:
        """POST a rendered email to the shared mailbox's sendMail endpoint.

        Raises:
            NotificationDeliveryError: When the request errors or returns non-202.
        """
        token = self._credential.get_token(_GRAPH_SCOPE).token
        payload = {
            "message": {
                "subject": content.subject,
                "body": {"contentType": "HTML", "content": content.html},
                "toRecipients": [{"emailAddress": {"address": to_email}}],
            },
            "saveToSentItems": False,
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        url = f"{self._base_url}/users/{self._mailbox}/sendMail"

        client = self._client or httpx.Client(timeout=_SEND_TIMEOUT_SECONDS)
        try:
            response = client.post(url, headers=headers, json=payload)
            if response.status_code != _ACCEPTED:
                raise NotificationDeliveryError(
                    f"Graph sendMail returned {response.status_code}"
                )
        except NotificationDeliveryError:
            raise
        except Exception as error:  # noqa: BLE001 — normalize all delivery failures
            raise NotificationDeliveryError("failed to send email via Microsoft Graph") from error
        finally:
            if self._client is None:
                client.close()
