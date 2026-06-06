"""RabbitMQ JobQueue adapter for local Docker Compose development."""

import json
from collections.abc import Callable
from typing import Any

import pika

from app.adapters.boundary_validation import parse_queue_message_body, validate_queue_message


class RabbitMQJobQueue:
    """JobQueue backed by a durable RabbitMQ queue via Pika BlockingConnection.

    Publish/consume patterns follow Pika blocking adapter docs:
    https://github.com/pika/pika/blob/main/docs/modules/adapters/blocking.md
    """

    def __init__(self, rabbitmq_url: str, queue_name: str) -> None:
        """Configure queue name and broker URL.

        Args:
            rabbitmq_url: AMQP connection URL (e.g. ``amqp://user:pass@rabbitmq:5672/``).
            queue_name: Durable queue name for Analysis Run messages.
        """
        self._rabbitmq_url = rabbitmq_url
        self._queue_name = queue_name

    def _connect(self) -> tuple[pika.BlockingConnection, pika.adapters.blocking_connection.BlockingChannel]:
        """Open a blocking AMQP connection and declare the work queue."""
        parameters = pika.URLParameters(self._rabbitmq_url)
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        channel.queue_declare(queue=self._queue_name, durable=True)
        return connection, channel

    def publish(self, message: dict[str, Any]) -> None:
        """Publish a JSON payload to the configured durable queue."""
        validated = validate_queue_message(message)
        body = json.dumps(validated).encode("utf-8")
        connection, channel = self._connect()
        try:
            channel.basic_publish(
                exchange="",
                routing_key=self._queue_name,
                body=body,
                properties=pika.BasicProperties(
                    delivery_mode=pika.DeliveryMode.Persistent,
                    content_type="application/json",
                ),
            )
        finally:
            connection.close()

    def consume(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Block and invoke ``handler`` for each delivered message until interrupted."""

        def on_message(
            channel: pika.adapters.blocking_connection.BlockingChannel,
            method: pika.spec.Basic.Deliver,
            _properties: pika.BasicProperties,
            body: bytes,
        ) -> None:
            payload = parse_queue_message_body(body)
            handler(payload)
            channel.basic_ack(delivery_tag=method.delivery_tag)

        connection, channel = self._connect()
        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(queue=self._queue_name, on_message_callback=on_message, auto_ack=False)
        try:
            channel.start_consuming()
        except KeyboardInterrupt:
            channel.stop_consuming()
        finally:
            connection.close()
