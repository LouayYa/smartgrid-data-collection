import json
from unittest.mock import MagicMock, patch

import pytest

from app.events import KafkaPublishError, ReadingPublisher, READINGS_TOPIC
from app.schemas import ReadingCreate


def _reading(meter_id=1):
    return ReadingCreate(
        meter_id=meter_id,
        timestamp="2007-01-01T00:00:00",
        global_active_power=1.5,
        voltage=240.0,
        sub_metering_1=0.0,
        sub_metering_2=1.0,
        sub_metering_3=17.0,
    )


def test_publish_produces_keyed_json_messages():
    fake = MagicMock()
    fake.flush.return_value = 0

    with patch("app.events.Producer", return_value=fake):
        count = ReadingPublisher().publish([_reading(1), _reading(2)])

    assert count == 2
    assert fake.produce.call_count == 2
    first = fake.produce.call_args_list[0]
    assert first.args[0] == READINGS_TOPIC
    assert first.kwargs["key"] == "1"
    payload = json.loads(first.kwargs["value"])
    assert payload["meter_id"] == 1
    assert payload["timestamp"] == "2007-01-01T00:00:00"


def test_publish_raises_when_messages_left_unflushed():
    fake = MagicMock()
    fake.flush.return_value = 3  # broker never acknowledged

    with patch("app.events.Producer", return_value=fake):
        with pytest.raises(KafkaPublishError):
            ReadingPublisher().publish([_reading()])


def test_publish_raises_on_delivery_error():
    fake = MagicMock()
    fake.flush.return_value = 0

    def produce(topic, key, value, on_delivery):
        on_delivery(Exception("broker rejected message"), None)

    fake.produce.side_effect = produce

    with patch("app.events.Producer", return_value=fake):
        with pytest.raises(KafkaPublishError):
            ReadingPublisher().publish([_reading()])


def test_producer_is_created_once():
    fake = MagicMock()
    fake.flush.return_value = 0

    publisher = ReadingPublisher()
    with patch("app.events.Producer", return_value=fake) as producer_cls:
        publisher.publish([_reading()])
        publisher.publish([_reading()])

    assert producer_cls.call_count == 1
