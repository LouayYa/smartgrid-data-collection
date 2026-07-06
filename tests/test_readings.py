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
