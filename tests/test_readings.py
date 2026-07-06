from datetime import datetime

from app.models import Reading


def _seed_reading(db, meter_id=1, timestamp="2024-01-15T10:30:00"):
    reading = Reading(
        meter_id=meter_id,
        timestamp=datetime.fromisoformat(timestamp),
        global_active_power=1.25,
        voltage=241.5,
        sub_metering_1=0.0,
        sub_metering_2=1.0,
        sub_metering_3=17.0,
    )
    db.add(reading)
    db.commit()
    return reading


def test_create_reading_publishes_event(client, fake_publisher):
    payload = {
        "meter_id": 1,
        "timestamp": "2024-01-15T10:30:00",
        "global_active_power": 1.25,
        "voltage": 241.5,
        "sub_metering_1": 0.0,
        "sub_metering_2": 1.0,
        "sub_metering_3": 17.0
    }
    response = client.post("/readings", json=payload)
    assert response.status_code == 202
    assert response.json() == {"accepted": 1, "status": "queued"}

    # The API never writes to the DB — it publishes for the consumer.
    assert len(fake_publisher.published) == 1
    event = fake_publisher.published[0]
    assert event.meter_id == 1
    assert event.global_active_power == 1.25


def test_bulk_readings_publish_events(client, fake_publisher):
    payload = [
        {
            "meter_id": 2,
            "timestamp": f"2024-01-15T11:0{i}:00",
            "global_active_power": 2.10,
            "voltage": 239.0,
            "sub_metering_1": 0.0,
            "sub_metering_2": 0.0,
            "sub_metering_3": 18.0
        }
        for i in range(3)
    ]
    response = client.post("/readings/bulk", json=payload)
    assert response.status_code == 202
    assert response.json() == {"accepted": 3, "status": "queued"}
    assert [e.meter_id for e in fake_publisher.published] == [2, 2, 2]


def test_create_reading_rejects_invalid_payload(client, fake_publisher):
    response = client.post("/readings", json={"meter_id": "not-a-number"})
    assert response.status_code == 422
    assert fake_publisher.published == []


def test_get_readings_for_meter(client, db):
    _seed_reading(db, meter_id=2, timestamp="2024-01-15T11:00:00")

    response = client.get("/readings", params={"meter_id": 2})
    assert response.status_code == 200
    readings = response.json()
    assert len(readings) == 1
    assert readings[0]["meter_id"] == 2


def test_get_readings_nonexistent_meter(client):
    response = client.get("/readings", params={"meter_id": 999999})
    assert response.status_code == 200
    assert response.json() == []


def test_get_readings_paginates(client, db):
    for minute in range(5):
        _seed_reading(db, meter_id=7, timestamp=f"2024-01-15T10:0{minute}:00")

    page1 = client.get("/readings", params={"meter_id": 7, "limit": 2, "offset": 0}).json()
    page2 = client.get("/readings", params={"meter_id": 7, "limit": 2, "offset": 2}).json()
    page3 = client.get("/readings", params={"meter_id": 7, "limit": 2, "offset": 4}).json()

    assert [len(page1), len(page2), len(page3)] == [2, 2, 1]
    # Ordered by timestamp, no overlap between pages.
    ids = [r["reading_id"] for r in page1 + page2 + page3]
    assert len(set(ids)) == 5


def test_get_readings_rejects_bad_limit(client):
    assert client.get("/readings", params={"limit": 0}).status_code == 422
    assert client.get("/readings", params={"limit": 100001}).status_code == 422


def test_get_single_reading_and_404(client, db):
    reading = _seed_reading(db, meter_id=3)

    ok = client.get(f"/readings/{reading.reading_id}")
    assert ok.status_code == 200
    assert ok.json()["meter_id"] == 3

    assert client.get("/readings/999999").status_code == 404


def test_delete_reading(client, db):
    reading = _seed_reading(db, meter_id=4)

    response = client.delete(f"/readings/{reading.reading_id}")
    assert response.status_code == 200
    assert client.get(f"/readings/{reading.reading_id}").status_code == 404

    assert client.delete("/readings/999999").status_code == 404


def test_delete_readings_by_meter(client, db):
    _seed_reading(db, meter_id=5, timestamp="2024-01-15T10:00:00")
    _seed_reading(db, meter_id=5, timestamp="2024-01-15T10:01:00")
    _seed_reading(db, meter_id=6, timestamp="2024-01-15T10:00:00")

    response = client.delete("/readings/by-meter/5")
    assert response.status_code == 200
    assert response.json()["deleted"] == 2
    assert client.get("/readings", params={"meter_id": 6}).json() != []


def test_delete_all_readings(client, db):
    _seed_reading(db, meter_id=1)
    _seed_reading(db, meter_id=2, timestamp="2024-01-15T11:00:00")

    response = client.delete("/readings")
    assert response.status_code == 200
    assert response.json()["deleted"] == 2
    assert client.get("/readings").json() == []


def test_bulk_returns_503_when_kafka_unavailable(client, fake_publisher):
    from app.events import KafkaPublishError

    def fail(readings):
        raise KafkaPublishError("broker unreachable")

    fake_publisher.publish = fail
    payload = [{
        "meter_id": 1,
        "timestamp": "2024-01-15T10:30:00",
        "global_active_power": 1.25,
        "voltage": 241.5,
        "sub_metering_1": 0.0,
        "sub_metering_2": 1.0,
        "sub_metering_3": 17.0
    }]
    assert client.post("/readings/bulk", json=payload).status_code == 503


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
