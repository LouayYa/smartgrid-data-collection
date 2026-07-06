import logging
import os
import time
from datetime import datetime, timedelta
from typing import List, Optional

import requests
from fastapi import FastAPI, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database import engine, get_db, Base
from app.events import KafkaPublishError, ReadingPublisher, get_publisher
from app.models import AnalyticsDaily, Reading
from app.schemas import (
    DailyAggregateResponse,
    ReadingCreate,
    ReadingResponse,
    SimulateRequest,
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("collection")

# SQLite (dev/test fallback) gets its schema from the models directly;
# Postgres schema is managed by Alembic migrations (alembic upgrade head).
if engine.url.get_backend_name() == "sqlite":
    Base.metadata.create_all(bind=engine)

app = FastAPI(title="Data Collection Service", version="1.0.0")

DATA_INGESTION_URL = os.getenv("DATA_INGESTION_URL", "http://localhost:8001")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s -> %d (%.1f ms)",
        request.method, request.url.path, response.status_code, elapsed_ms,
    )
    return response


def _parse_query_date(value: str, name: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{name} must be in YYYY-MM-DD format")


def _parse_ingestion_timestamp(date_str: str, time_str: str) -> datetime:
    # ISO first (the ingestion service's canonical format), then the source
    # dataset's d/m/yyyy and d/m/yy for compatibility.
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            d = datetime.strptime(date_str.strip(), fmt)
            t = datetime.strptime(time_str.strip(), "%H:%M:%S").time()
            return datetime.combine(d.date(), t)
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date: {date_str!r}")


@app.get("/health")
def health():
    return {"status": "ok"}


# --- Write Endpoints (publish to Kafka; app/consumer.py persists) ---

@app.post("/readings", status_code=202)
def create_reading(
    reading: ReadingCreate,
    publisher: ReadingPublisher = Depends(get_publisher),
):
    try:
        publisher.publish([reading])
    except KafkaPublishError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"accepted": 1, "status": "queued"}


@app.post("/readings/bulk", status_code=202)
def create_readings_bulk(
    readings: List[ReadingCreate],
    publisher: ReadingPublisher = Depends(get_publisher),
):
    try:
        accepted = publisher.publish(readings)
    except KafkaPublishError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"accepted": accepted, "status": "queued"}


@app.get("/readings", response_model=List[ReadingResponse])
def get_readings(
    meter_id: Optional[int] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(1000, ge=1, le=100000, description="Max records per page."),
    offset: int = Query(0, ge=0, description="Number of records to skip."),
    db: Session = Depends(get_db),
):
    query = db.query(Reading)
    if meter_id is not None:
        query = query.filter(Reading.meter_id == meter_id)
    if start_date:
        query = query.filter(Reading.timestamp >= _parse_query_date(start_date, "start_date"))
    if end_date:
        # Compare against the start of the next day so the whole end date is included.
        end = _parse_query_date(end_date, "end_date") + timedelta(days=1)
        query = query.filter(Reading.timestamp < end)
    return (
        query.order_by(Reading.timestamp, Reading.reading_id)
        .offset(offset)
        .limit(limit)
        .all()
    )


@app.get("/readings/{reading_id}", response_model=ReadingResponse)
def get_reading(reading_id: int, db: Session = Depends(get_db)):
    reading = db.query(Reading).filter(Reading.reading_id == reading_id).first()
    if not reading:
        raise HTTPException(status_code=404, detail="Reading not found")
    return reading


@app.delete("/readings/{reading_id}")
def delete_reading(reading_id: int, db: Session = Depends(get_db)):
    reading = db.query(Reading).filter(Reading.reading_id == reading_id).first()
    if not reading:
        raise HTTPException(status_code=404, detail="Reading not found")
    db.delete(reading)
    db.commit()
    return {"reading_id": reading_id, "status": "deleted"}


@app.delete("/readings/by-meter/{meter_id}")
def delete_readings_by_meter(meter_id: int, db: Session = Depends(get_db)):
    count = db.query(Reading).filter(Reading.meter_id == meter_id).delete()
    db.commit()
    return {"meter_id": meter_id, "deleted": count}


@app.delete("/readings")
def delete_all_readings(db: Session = Depends(get_db)):
    count = db.query(Reading).delete()
    db.commit()
    return {"deleted": count}


# --- Batch Aggregates (written by the Airflow daily_consumption_aggregates DAG) ---

@app.get("/aggregates/daily", response_model=List[DailyAggregateResponse])
def get_daily_aggregates(
    meter_id: Optional[int] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(AnalyticsDaily)
    if meter_id is not None:
        query = query.filter(AnalyticsDaily.meter_id == meter_id)
    if start_date:
        query = query.filter(AnalyticsDaily.day >= _parse_query_date(start_date, "start_date").date())
    if end_date:
        query = query.filter(AnalyticsDaily.day <= _parse_query_date(end_date, "end_date").date())
    return query.order_by(AnalyticsDaily.meter_id, AnalyticsDaily.day).all()


# --- Simulation Endpoint ---

@app.post("/simulate/{meter_id}", status_code=202)
def simulate(
    meter_id: int,
    body: Optional[SimulateRequest] = None,
    publisher: ReadingPublisher = Depends(get_publisher),
):
    start_str = (body.start_date if body and body.start_date else None) or "2007-01-01"
    start_dt = _parse_query_date(start_str, "start_date")
    if body and body.end_date:
        end_dt = _parse_query_date(body.end_date, "end_date")
    else:
        end_dt = start_dt + timedelta(days=10)

    params = {
        "start_date": start_dt.strftime("%Y-%m-%d"),
        "end_date": end_dt.strftime("%Y-%m-%d"),
        "limit": 100000,
    }

    try:
        resp = requests.get(f"{DATA_INGESTION_URL}/api/v1/consumption", params=params, timeout=240)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch from ingestion service: {e}")

    records = resp.json()

    events = []
    for record in records:
        try:
            ts = _parse_ingestion_timestamp(record["Date"], record["Time"])
        except (KeyError, ValueError):
            continue
        events.append(ReadingCreate(
            meter_id=meter_id,
            timestamp=ts,
            global_active_power=float(record.get("Global_active_power") or 0),
            voltage=float(record.get("Voltage") or 0),
            sub_metering_1=float(record.get("Sub_metering_1") or 0),
            sub_metering_2=float(record.get("Sub_metering_2") or 0),
            sub_metering_3=float(record.get("Sub_metering_3") or 0),
        ))

    try:
        published = publisher.publish(events)
    except KafkaPublishError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return {
        "meter_id": meter_id,
        "status": "simulation_published",
        "records_published": published,
    }
