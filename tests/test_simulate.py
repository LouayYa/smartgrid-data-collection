from datetime import datetime
from unittest.mock import patch, MagicMock


def test_simulate_publishes_readings(client, fake_publisher):
    # Mock the external call to the Data Ingestion service
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = [
        {
            "Date": "1/1/2007",
            "Time": "00:00:00",
            "Global_active_power": 1.5,
            "Voltage": 240.0,
            "Sub_metering_1": 0,
            "Sub_metering_2": 1,
            "Sub_metering_3": 17,
        }
    ]

    with patch("app.main.requests.get", return_value=mock_response):
        response = client.post("/simulate/1")
        assert response.status_code == 202
        body = response.json()
        assert body["meter_id"] == 1
        assert body["status"] == "simulation_published"
        assert body["records_published"] == 1

    # The endpoint publishes to Kafka instead of writing to the DB.
    assert len(fake_publisher.published) == 1
    event = fake_publisher.published[0]
    assert event.meter_id == 1
    assert event.timestamp == datetime(2007, 1, 1, 0, 0, 0)
    assert event.global_active_power == 1.5


def test_simulate_skips_malformed_records(client, fake_publisher):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = [
        {"Date": "not-a-date", "Time": "00:00:00"},
        {
            "Date": "2/1/2007",
            "Time": "00:01:00",
            "Global_active_power": 2.0,
            "Voltage": 241.0,
            "Sub_metering_1": 0,
            "Sub_metering_2": 0,
            "Sub_metering_3": 0,
        },
    ]

    with patch("app.main.requests.get", return_value=mock_response):
        response = client.post("/simulate/3")
        assert response.status_code == 202
        assert response.json()["records_published"] == 1

    assert len(fake_publisher.published) == 1
    assert fake_publisher.published[0].timestamp == datetime(2007, 1, 2, 0, 1, 0)


def test_simulate_invalid_meter(client):
    response = client.post("/simulate/not-a-number")
    assert response.status_code == 422


def test_simulate_rejects_bad_dates(client):
    response = client.post("/simulate/1", json={"start_date": "not-a-date"})
    assert response.status_code == 400


def test_simulate_returns_502_when_ingestion_unreachable(client):
    import requests as requests_lib

    with patch("app.main.requests.get", side_effect=requests_lib.ConnectionError("down")):
        response = client.post("/simulate/1")
    assert response.status_code == 502
