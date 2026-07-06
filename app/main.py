import os
from datetime import datetime, timedelta
from typing import List, Optional

import requests
from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import engine, get_db, Base
from app.models import Reading
from app.schemas import ReadingCreate, ReadingResponse, SimulateRequest

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Data Collection Service", version="1.0.0")

DATA_INGESTION_URL = os.getenv("DATA_INGESTION_URL", "http://localhost:8001")
SIMULATE_BATCH_SIZE = 5000


def _parse_query_date(value: str, name: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{name} must be in YYYY-MM-DD format")


def _parse_ingestion_timestamp(date_str: str, time_str: str) -> datetime:
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            d = datetime.strptime(date_str.strip(), fmt)
            t = datetime.strptime(time_str.strip(), "%H:%M:%S").time()
            return datetime.combine(d.date(), t)
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date: {date_str!r}")


# --- CRUD Endpoints ---

@app.post("/readings", response_model=ReadingResponse, status_code=201)
def create_reading(reading: ReadingCreate, db: Session = Depends(get_db)):
    db_reading = Reading(**reading.model_dump())
    db.add(db_reading)
    db.commit()
    db.refresh(db_reading)
    return db_reading


@app.post("/readings/bulk", status_code=201)
def create_readings_bulk(readings: List[ReadingCreate], db: Session = Depends(get_db)):
    objects = [Reading(**r.model_dump()) for r in readings]
    db.bulk_save_objects(objects)
    db.commit()
    return {"inserted": len(objects), "status": "stored"}


@app.get("/readings", response_model=List[ReadingResponse])
def get_readings(
    meter_id: Optional[int] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
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
    return query.all()


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


# --- Simulation Endpoint ---

@app.post("/simulate/{meter_id}")
def simulate(meter_id: int, body: Optional[SimulateRequest] = None, db: Session = Depends(get_db)):
    start_str = (body.start_date if body and body.start_date else None) or "2007-01-01"
    start_dt = _parse_query_date(start_str, "start_date")
    if body and body.end_date:
        end_dt = _parse_query_date(body.end_date, "end_date")
    else:
        end_dt = start_dt + timedelta(days=10)

    params = {
        "start_date": f"{start_dt.day}/{start_dt.month}/{start_dt.year}",
        "end_date": f"{end_dt.day}/{end_dt.month}/{end_dt.year}",
        "limit": 100000,
    }

    try:
        resp = requests.get(f"{DATA_INGESTION_URL}/api/v1/consumption", params=params, timeout=240)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch from ingestion service: {e}")

    records = resp.json()

    rows = []
    for record in records:
        try:
            ts = _parse_ingestion_timestamp(record["Date"], record["Time"])
        except (KeyError, ValueError):
            continue
        rows.append(Reading(
            meter_id=meter_id,
            timestamp=ts,
            global_active_power=float(record.get("Global_active_power") or 0),
            voltage=float(record.get("Voltage") or 0),
            sub_metering_1=float(record.get("Sub_metering_1") or 0),
            sub_metering_2=float(record.get("Sub_metering_2") or 0),
            sub_metering_3=float(record.get("Sub_metering_3") or 0),
        ))

    for i in range(0, len(rows), SIMULATE_BATCH_SIZE):
        db.bulk_save_objects(rows[i : i + SIMULATE_BATCH_SIZE])
        db.commit()

    return {
        "meter_id": meter_id,
        "status": "simulation_complete",
        "records_inserted": len(rows),
    }
