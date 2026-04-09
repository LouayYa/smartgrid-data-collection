import os
import subprocess
import sys
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import engine, get_db, Base
from app.models import Reading
from app.schemas import ReadingCreate, ReadingResponse, SimulateRequest

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Data Collection Service", version="1.0.0")

DATA_INGESTION_URL = os.getenv("DATA_INGESTION_URL", "http://localhost:8001")


# --- CRUD Endpoints ---

@app.post("/readings", response_model=ReadingResponse, status_code=201)
def create_reading(reading: ReadingCreate, db: Session = Depends(get_db)):
    db_reading = Reading(**reading.model_dump())
    db.add(db_reading)
    db.commit()
    db.refresh(db_reading)
    return db_reading


@app.get("/readings", response_model=list[ReadingResponse])
def get_readings(
    meter_id: int | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(Reading)
    if meter_id is not None:
        query = query.filter(Reading.meter_id == meter_id)
    if start_date:
        query = query.filter(Reading.timestamp >= datetime.strptime(start_date, "%Y-%m-%d"))
    if end_date:
        query = query.filter(Reading.timestamp <= datetime.strptime(end_date, "%Y-%m-%d"))
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


# --- Simulation Endpoint ---

@app.post("/simulate/{meter_id}")
def simulate(meter_id: int, body: SimulateRequest | None = None):
    simulator_path = os.path.join(os.path.dirname(__file__), "..", "simulator", "client.py")
    cmd = [sys.executable, simulator_path, str(meter_id)]

    if body and body.start_date:
        cmd.extend(["--start-date", body.start_date])
    if body and body.end_date:
        cmd.extend(["--end-date", body.end_date])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            env={**os.environ, "DATA_INGESTION_URL": DATA_INGESTION_URL,
                 "DATA_COLLECTION_URL": f"http://localhost:{os.getenv('PORT', '8002')}"},
        )
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Simulator error: {result.stderr}")
        return {
            "meter_id": meter_id,
            "status": "simulation_started",
            "output": result.stdout,
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Simulation timed out")
