import json
from datetime import datetime

from app.consumer import parse_message, persist_batch
from app.models import Reading


class FakeMessage:
    """Minimal stand-in for a confluent_kafka Message."""

    def __init__(self, value):
        self._value = value

    def value(self):
        return self._value

    def topic(self):
        return "meter-readings"

    def partition(self):
        return 0

    def offset(self):
        return 42


VALID_PAYLOAD = {
    "meter_id": 1,
    "timestamp": "2007-01-01T00:00:00",
    "global_active_power": 1.5,
    "voltage": 240.0,
    "sub_metering_1": 0.0,
    "sub_metering_2": 1.0,
    "sub_metering_3": 17.0,
}


def test_parse_message_valid():
    msg = FakeMessage(json.dumps(VALID_PAYLOAD).encode())
    row = parse_message(msg)
    assert isinstance(row, Reading)
    assert row.meter_id == 1
    assert row.timestamp == datetime(2007, 1, 1, 0, 0, 0)
    assert row.global_active_power == 1.5


def test_parse_message_malformed_json():
    assert parse_message(FakeMessage(b"not json at all")) is None


def test_parse_message_schema_violation():
    bad = dict(VALID_PAYLOAD, meter_id="not-a-number")
    assert parse_message(FakeMessage(json.dumps(bad).encode())) is None


def test_parse_message_missing_fields():
    assert parse_message(FakeMessage(json.dumps({"meter_id": 1}).encode())) is None


def test_persist_batch_writes_rows(db):
    rows = [
        Reading(
            meter_id=1,
            timestamp=datetime(2007, 1, 1, 0, minute),
            global_active_power=1.0,
            voltage=240.0,
            sub_metering_1=0.0,
            sub_metering_2=0.0,
            sub_metering_3=0.0,
        )
        for minute in range(3)
    ]
    assert persist_batch(db, rows) == 3
    assert db.query(Reading).count() == 3


def test_persist_batch_empty(db):
    assert persist_batch(db, []) == 0
    assert db.query(Reading).count() == 0
