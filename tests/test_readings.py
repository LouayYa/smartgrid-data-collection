def test_create_reading(client):
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
    assert response.status_code == 201
    data = response.json()
    assert data["meter_id"] == 1
    assert data["global_active_power"] == 1.25


def test_get_readings_for_meter(client):
    # Create a reading first
    payload = {
        "meter_id": 2,
        "timestamp": "2024-01-15T11:00:00",
        "global_active_power": 2.10,
        "voltage": 239.0,
        "sub_metering_1": 0.0,
        "sub_metering_2": 0.0,
        "sub_metering_3": 18.0
    }
    client.post("/readings", json=payload)

    response = client.get("/readings", params={"meter_id": 2})
    assert response.status_code == 200
    readings = response.json()
    assert len(readings) >= 1
    assert readings[0]["meter_id"] == 2


def test_get_readings_nonexistent_meter(client):
    response = client.get("/readings", params={"meter_id": 999999})
    assert response.status_code == 200
    assert response.json() == []
