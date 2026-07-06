# SmartGrid Insights — Data Collection Service

> **Service 3 of 5** | CMP404 Spring 2026 · Team 5 | Developed by **Louy Abbas** · AUS

## Overview

One of five independently deployed microservices behind SmartGrid Insights, a system that ingests, stores, and analyzes 260K+ smart meter readings end to end. This service is the write path: it receives readings from the client simulator, exposes a simulation-trigger endpoint that pulls historical consumption data from the Data Ingestion Service, persists it to PostgreSQL, and serves it back out to the Data Analysis Service.

Originally deployed on Azure App Service with Azure SQL; the database layer has since been migrated to **PostgreSQL**, and the service carries a **pytest** suite covering its API surface (CRUD on readings, simulation triggering, input validation) against an isolated SQLite test database — no live infrastructure required to run tests locally or in CI.

**Stack:** FastAPI · SQLAlchemy · PostgreSQL (psycopg2) · Pydantic · pytest · Docker · GitHub Actions · Azure App Service (deploy-on-demand)

---

## Data Flow

```
Client Interface
      │
      ├──► POST /simulate/{meter_id} ──► fetches historical data
      │                                        │
      │                                        ├── GET /consumption  (Data Ingestion Service)
      │                                        └── bulk-inserts as readings (this service's DB)
      │
      └──► Data Analysis Service  ──► queries this service via GET /readings
```

A standalone simulator client ([`simulator/client.py`](simulator/client.py)) is also available — it performs the same replay from outside the service by POSTing to `/readings/bulk`.

---

## API Endpoints

Base URL: `http://localhost:8002` (local dev — the Azure deployment has been decommissioned; see [CI/CD](#cicd))

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/readings` | Store a single reading |
| `POST` | `/readings/bulk` | Store a batch of readings (used by the standalone simulator client) |
| `GET` | `/readings` | Get readings — optional `meter_id`, `start_date`, `end_date` (`YYYY-MM-DD`, both inclusive) filters |
| `GET` | `/readings/{id}` | Get a specific reading |
| `DELETE` | `/readings/{id}` | Delete a reading |
| `DELETE` | `/readings/by-meter/{meter_id}` | Delete all readings for a meter |
| `DELETE` | `/readings` | Delete all readings |
| `POST` | `/simulate/{meter_id}` | Replay historical data from the Data Ingestion Service as readings for this meter — optional `start_date`/`end_date` body fields (defaults to a 10-day window) |

**Example — trigger simulation:**
```http
POST /simulate/3
{ "start_date": "2007-01-01", "end_date": "2007-01-08" }
```
```json
{ "meter_id": 3, "status": "simulation_complete", "records_inserted": 10080 }
```

---

## Database Schema

**Table: `readings`** (PostgreSQL)

| Column | Type | Description |
|---|---|---|
| `reading_id` | SERIAL PK | Auto-increment |
| `meter_id` | INTEGER | References a registered meter |
| `timestamp` | TIMESTAMP | Reading timestamp |
| `global_active_power` | FLOAT | Total active power (kW) |
| `voltage` | FLOAT | Voltage (V) |
| `sub_metering_1/2/3` | FLOAT | Kitchen / Laundry / Water heater (Wh) |

Schema is created automatically on startup via `Base.metadata.create_all()` — no manual migration step needed for this table.

---

## Testing

The service ships with a `pytest` suite in [`tests/`](tests/) covering:

- **CRUD on readings** — creating a reading, filtering by `meter_id`, and the empty-result case for a meter with no data (`tests/test_readings.py`)
- **Simulation triggering** — mocking the outbound call to the Data Ingestion Service and asserting readings are correctly parsed and persisted, plus input-validation behavior for malformed meter IDs (`tests/test_simulate.py`)

Tests run against an isolated, disposable **SQLite** database (`tests/conftest.py` overrides `DATABASE_URL` before the app is imported), not the real PostgreSQL instance — so they're fast, deterministic, and require no external services or credentials to run.

```bash
pip install pytest httpx
pytest tests/ -v
```

This suite runs automatically as part of CI (see below) on every push to `main`.

---

## Local Setup

```bash
git clone https://github.com/LouayYa/smartgrid-data-collection.git
cd smartgrid-data-collection
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file:
```env
DATABASE_URL=postgresql://<user>:<password>@<host>:5432/smartgrid_collection
DATA_INGESTION_URL=http://localhost:8001
```
Without `DATABASE_URL`, the service falls back to a local SQLite file — handy for a quick look without Postgres.

Run:
```bash
uvicorn app.main:app --reload --port 8002
# Docs: http://localhost:8002/docs
```

---

## Run with Docker

The repo ships a multi-stage [`Dockerfile`](Dockerfile) (Python 3.12-slim builder + slim runtime, non-root user, uvicorn):

```bash
docker build -t smartgrid-data-collection .
docker run -p 8002:8002 --env-file .env smartgrid-data-collection
```

To run the **entire five-service stack plus a shared PostgreSQL 16 instance** with one command, use the `docker-compose.yml` in the umbrella repo: [SmartGrid-Insights](https://github.com/LouayYa/SmartGrid-Insights).

---

## CI/CD

**Build & test** run automatically via **GitHub Actions** on every push to `main`: dependencies install into a virtual environment and the `pytest` suite runs against the isolated SQLite test database described above. A failing test blocks the pipeline before any deployment step runs.

**Deploy to Azure App Service** was originally wired through **Azure Deployment Center** (GitHub source → auto-generated workflow), with app settings (`DATABASE_URL`, `DATA_INGESTION_URL`) configured under App Service → Configuration rather than committed to the repo. The live Azure App Service has since been decommissioned to cut hosting costs, so the `deploy` job is kept in [`.github/workflows/`](.github/workflows/) as a reference implementation and only runs on a manual `workflow_dispatch` trigger — it no longer fires on every push.

---

## Related Services

| Service | Owner | Role |
|---|---|---|
| Data Ingestion Service | Saif | Historical CSV data source |
| Meter Registration Service | Ahmad | Provides `meter_id` values |
| **Data Collection Service** | **Louy** | This repo |
| Data Analysis Service | Louy | Queries this DB for analytics |
| Client Interface | Ahmad | Web UI |

> Part of **SmartGrid Insights** — CMP404 Spring 2026 · Team 5  
> Saifeldin Hassan · Louy Abbas · Ahmad Bilal · American University of Sharjah
