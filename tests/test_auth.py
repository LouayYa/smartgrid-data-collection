def test_requires_api_key_when_configured(client, monkeypatch):
    monkeypatch.setattr("app.main.API_KEY", "sekrit")

    assert client.get("/readings").status_code == 401
    assert client.get("/readings", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/readings", headers={"X-API-Key": "sekrit"}).status_code == 200
    # Probes and docs stay open.
    assert client.get("/health").status_code == 200


def test_auth_disabled_when_key_unset(client):
    assert client.get("/readings").status_code == 200
