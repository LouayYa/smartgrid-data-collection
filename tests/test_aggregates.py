from datetime import date, datetime

from app.models import AnalyticsDaily


def _seed_aggregate(db, meter_id=1, day=date(2007, 1, 1), avg_power=1.5):
    row = AnalyticsDaily(
        meter_id=meter_id,
        day=day,
        avg_power=avg_power,
        peak_power=3.2,
        kitchen_wh=10.0,
        laundry_wh=5.0,
        water_heater_ac_wh=20.0,
        samples=1440,
        computed_at=datetime(2026, 7, 6, 2, 0, 0),
    )
    db.add(row)
    db.commit()
    return row


def test_daily_aggregates_filter_by_meter_and_range(client, db):
    _seed_aggregate(db, meter_id=1, day=date(2007, 1, 1))
    _seed_aggregate(db, meter_id=1, day=date(2007, 1, 2))
    _seed_aggregate(db, meter_id=1, day=date(2007, 2, 1))
    _seed_aggregate(db, meter_id=2, day=date(2007, 1, 1))

    response = client.get("/aggregates/daily", params={
        "meter_id": 1, "start_date": "2007-01-01", "end_date": "2007-01-31",
    })

    assert response.status_code == 200
    rows = response.json()
    assert [r["day"] for r in rows] == ["2007-01-01", "2007-01-02"]
    assert all(r["meter_id"] == 1 for r in rows)
    assert rows[0]["avg_power"] == 1.5
    assert rows[0]["samples"] == 1440


def test_daily_aggregates_empty(client):
    response = client.get("/aggregates/daily", params={"meter_id": 99})
    assert response.status_code == 200
    assert response.json() == []


def test_daily_aggregates_rejects_bad_date(client):
    response = client.get("/aggregates/daily", params={"start_date": "nope"})
    assert response.status_code == 400
