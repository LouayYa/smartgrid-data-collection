"""Kafka publishing for meter readings.

All reading writes flow through the `meter-readings` topic: the REST API and
the simulation endpoint only ever *publish* events, and the consumer worker
(app/consumer.py) is the single component that persists them to the database.
"""
import os
from typing import Iterable, List

from confluent_kafka import Producer

from app.schemas import ReadingCreate

READINGS_TOPIC = os.getenv("KAFKA_READINGS_TOPIC", "meter-readings")
BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

# Wait up to this long for the broker to acknowledge all queued messages.
FLUSH_TIMEOUT_SECONDS = 30


class KafkaPublishError(RuntimeError):
    """Raised when one or more readings could not be delivered to Kafka."""


class ReadingPublisher:
    """Publishes validated readings to the meter-readings topic.

    Messages are keyed by meter_id so all readings for a meter land on the
    same partition and stay ordered.
    """

    def __init__(self):
        self._producer = None

    def _get_producer(self) -> Producer:
        # Lazy so importing the app never requires a reachable broker.
        if self._producer is None:
            self._producer = Producer({
                "bootstrap.servers": BOOTSTRAP_SERVERS,
                "acks": "all",
                "enable.idempotence": True,
            })
        return self._producer

    def publish(self, readings: Iterable[ReadingCreate]) -> int:
        producer = self._get_producer()
        errors: List[Exception] = []

        def on_delivery(err, msg):
            if err is not None:
                errors.append(err)

        count = 0
        for reading in readings:
            while True:
                try:
                    producer.produce(
                        READINGS_TOPIC,
                        key=str(reading.meter_id),
                        value=reading.model_dump_json(),
                        on_delivery=on_delivery,
                    )
                    break
                except BufferError:
                    # Local queue full — serve delivery callbacks, then retry.
                    producer.poll(1)
            count += 1
            producer.poll(0)

        unflushed = producer.flush(FLUSH_TIMEOUT_SECONDS)
        if unflushed or errors:
            detail = errors[0] if errors else f"{unflushed} messages still queued"
            raise KafkaPublishError(f"Failed to deliver readings to Kafka: {detail}")
        return count


_publisher = ReadingPublisher()


def get_publisher() -> ReadingPublisher:
    """FastAPI dependency — overridden with a fake in tests."""
    return _publisher
