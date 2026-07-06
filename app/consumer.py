"""Kafka consumer worker — the single writer of readings to the database.

Reads JSON reading events from the meter-readings topic, validates them with
the same Pydantic schema the REST API uses, and persists them in batches.
Offsets are committed only after the batch is committed to Postgres, giving
at-least-once delivery (duplicates are acceptable for time-series readings).

Run as its own process (see the collection-consumer service in
docker-compose.yml):

    python -m app.consumer
"""
import json
import logging
import os
import signal
from typing import List, Optional

from confluent_kafka import Consumer
from pydantic import ValidationError

from app.database import Base, SessionLocal, engine
from app.events import BOOTSTRAP_SERVERS, READINGS_TOPIC
from app.models import Reading
from app.schemas import ReadingCreate

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("readings-consumer")

CONSUMER_GROUP = os.getenv("KAFKA_CONSUMER_GROUP", "data-collection-writers")
BATCH_SIZE = int(os.getenv("CONSUMER_BATCH_SIZE", "1000"))
POLL_TIMEOUT_SECONDS = 1.0

_running = True


def _stop(signum, frame):
    global _running
    log.info("Received signal %s, shutting down after current batch", signum)
    _running = False


def parse_message(msg) -> Optional[Reading]:
    """Validate one Kafka message into a Reading row, or None if malformed."""
    try:
        data = json.loads(msg.value())
        reading = ReadingCreate.model_validate(data)
    except (ValueError, TypeError, ValidationError) as e:
        log.warning(
            "Skipping malformed message %s[%s]@%s: %s",
            msg.topic(), msg.partition(), msg.offset(), e,
        )
        return None
    return Reading(**reading.model_dump())


def persist_batch(session, rows: List[Reading]) -> int:
    """Write a batch of rows in one transaction. Returns the number written."""
    if not rows:
        return 0
    session.bulk_save_objects(rows)
    session.commit()
    return len(rows)


def run():
    Base.metadata.create_all(bind=engine)

    consumer = Consumer({
        "bootstrap.servers": BOOTSTRAP_SERVERS,
        "group.id": CONSUMER_GROUP,
        "auto.offset.reset": "earliest",
        # Commit manually, only after the DB transaction succeeds.
        "enable.auto.commit": False,
    })
    consumer.subscribe([READINGS_TOPIC])
    log.info(
        "Consuming %s from %s as group %s",
        READINGS_TOPIC, BOOTSTRAP_SERVERS, CONSUMER_GROUP,
    )

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    batch: List[Reading] = []
    total = 0
    try:
        while _running:
            msg = consumer.poll(POLL_TIMEOUT_SECONDS)

            if msg is not None:
                if msg.error():
                    log.error("Kafka error: %s", msg.error())
                    continue
                row = parse_message(msg)
                if row is not None:
                    batch.append(row)

            # Flush when the batch is full, or when the topic goes quiet.
            if batch and (len(batch) >= BATCH_SIZE or msg is None):
                session = SessionLocal()
                try:
                    written = persist_batch(session, batch)
                finally:
                    session.close()
                consumer.commit(asynchronous=False)
                total += written
                log.info("Persisted %d readings (%d total)", written, total)
                batch = []
    finally:
        consumer.close()
        log.info("Consumer closed after persisting %d readings", total)


if __name__ == "__main__":
    run()
