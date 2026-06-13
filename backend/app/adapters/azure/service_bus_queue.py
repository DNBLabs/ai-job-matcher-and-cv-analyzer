"""Azure Service Bus JobQueue adapter (production, Managed Identity).

The API MI sends Analysis Run messages; the Worker MI receives them. Both use
the Container App Managed Identity with queue-scoped RBAC (Data Sender / Data
Receiver) — the only SAS key in the system is a Listen-only rule consumed by the
KEDA scaler, not by application code (ADR-0004; infra/app/identity.tf).

Messages are received in the default PEEK_LOCK mode and settled with
``complete_message`` after the handler returns; the worker's handler swallows and
logs its own errors, so an unhandled failure that escapes here lets the broker
redeliver up to ``max_delivery_count`` before dead-lettering.

``consume`` returns when the queue drains (an empty receive batch), which suits
KEDA scale-to-zero: the worker is started on queue depth, drains, and exits.

Source: https://learn.microsoft.com/en-us/python/api/overview/azure/servicebus-readme
    ServiceBusClient(fully_qualified_namespace, credential)
    .get_queue_sender(q).send_messages(ServiceBusMessage(body))
    .get_queue_receiver(q).receive_messages(max_message_count, max_wait_time)
"""

import json
import logging
from collections.abc import Callable
from typing import Any

from azure.core.credentials import TokenCredential
from azure.servicebus import ServiceBusClient, ServiceBusMessage

from app.adapters.boundary_validation import parse_queue_message_body, validate_queue_message

logger = logging.getLogger(__name__)

_RECEIVE_BATCH_SIZE = 1
_RECEIVE_MAX_WAIT_SECONDS = 30


class ServiceBusJobQueue:
    """JobQueue backed by an Azure Service Bus queue via Managed Identity."""

    def __init__(
        self,
        *,
        queue_name: str,
        fully_qualified_namespace: str | None = None,
        credential: TokenCredential | None = None,
        client: ServiceBusClient | None = None,
        max_wait_time: int = _RECEIVE_MAX_WAIT_SECONDS,
    ) -> None:
        """Bind to a queue; build a ServiceBusClient from MI unless one is injected.

        Args:
            queue_name: Service Bus queue name for Analysis Run messages.
            fully_qualified_namespace: ``<namespace>.servicebus.windows.net``. Required
                unless ``client`` is supplied.
            credential: Managed Identity credential. Required unless ``client`` is supplied.
            client: Pre-built ServiceBusClient-like object (used in tests). Its lifecycle
                is owned by the caller and not closed by this adapter.
            max_wait_time: Seconds a receive waits for messages before returning empty.

        Raises:
            ValueError: When neither a client nor namespace + credential is given.
        """
        if client is None and (not fully_qualified_namespace or credential is None):
            raise ValueError("ServiceBusJobQueue requires fully_qualified_namespace and credential")
        self._queue_name = queue_name
        self._namespace = fully_qualified_namespace
        self._credential = credential
        self._injected_client = client
        self._max_wait_time = max_wait_time

    def _build_client(self) -> ServiceBusClient:
        """Construct a ServiceBusClient bound to the Managed Identity credential."""
        return ServiceBusClient(
            fully_qualified_namespace=self._namespace,
            credential=self._credential,
        )

    def publish(self, message: dict[str, Any]) -> None:
        """Send a JSON payload to the queue as a single Service Bus message."""
        validated = validate_queue_message(message)
        body = json.dumps(validated)
        client = self._injected_client or self._build_client()
        try:
            with client.get_queue_sender(self._queue_name) as sender:
                sender.send_messages(ServiceBusMessage(body))
        finally:
            if self._injected_client is None:
                client.close()

    def consume(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Receive and process messages until the queue drains or SIGTERM arrives.

        Each message body is parsed to a JSON object, passed to ``handler``, then
        settled with ``complete_message``. Receiving stops when a batch comes back
        empty (queue drained) so the worker can exit and scale to zero.
        """
        client = self._injected_client or self._build_client()
        try:
            with client.get_queue_receiver(
                self._queue_name, max_wait_time=self._max_wait_time
            ) as receiver:
                while True:
                    batch = receiver.receive_messages(
                        max_message_count=_RECEIVE_BATCH_SIZE,
                        max_wait_time=self._max_wait_time,
                    )
                    if not batch:
                        break
                    for message in batch:
                        payload = parse_queue_message_body(str(message).encode("utf-8"))
                        handler(payload)
                        receiver.complete_message(message)
        except KeyboardInterrupt:
            logger.info("service bus consume interrupted — shutting down")
        finally:
            if self._injected_client is None:
                client.close()
