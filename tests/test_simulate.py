from unittest.mock import patch, MagicMock


def test_simulate_triggers_successfully(client):
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
        assert response.status_code == 200
        body = response.json()
        assert body["meter_id"] == 1
        assert body["status"] == "simulation_complete"
        assert body["records_inserted"] == 1


def test_simulate_invalid_meter(client):
    response = client.post("/simulate/not-a-number")
    assert response.status_code == 422
