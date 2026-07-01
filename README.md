# SmartGrid Insights — Data Collection Service

> **Service 3 of 5** | CMP404 Spring 2026 · Team 5 | Developed by **Louy Abbas** · AUS

## Overview

One of five independently deployed microservices behind SmartGrid Insights, a system that ingests, stores, and analyzes 260K+ smart meter readings end to end. This service is the write path: it receives readings from the client simulator, exposes a simulation-trigger endpoint that pulls historical consumption data from the Data Ingestion Service, persists it to PostgreSQL, and serves it back out to the Data Analysis Service.

Originally deployed on Azure App Service with Azure SQL; the database layer has since been migrated to **PostgreSQL**, and the service carries a **pytest** suite covering its API surface (CRUD on readings, simulation triggering, input validation) against an isolated SQLite test database — no live infrastructure required to run tests locally or in CI.

**Stack:** FastAPI · SQLAlchemy · PostgreSQL (psycopg2) · Pydantic · pytest · GitHub Actions · Azure App Service (deploy-on-demand)

---

## Data Flow

```
Client Interface
      │
      ├──► POST /simulate/{meter_id} ──► spawns Python Simulator
      │                                        │
      │                                        ├── GET /consumption  (Data Ingestion Service)
      │                                        └── POST /readings    (this service)
      │
      └──► Data Analysis Service  ──► queries this service's DB
```

---

## API Endpoints

Base URL: `http://localhost:8000` (local dev — the Azure deployment has been decommissioned; see [CI/CD](#cicd))

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/readings` | Store a reading (called by simulator) |
| `GET` | `/readings` | Get readings — optional `meter_id`, `start_date`, `end_date` filters |
| `GET` | `/readings/{id}` | Get a specific reading |
| `DELETE` | `/readings/{id}` | Delete a reading |
| `POST` | `/simulate/{meter_id}` | Trigger the Python simulator for a meter |

**Example — trigger simulation:**
```http
POST /simulate/3
```
```json
{ "meter_id": 3, "status": "simulation_started", "records": 10080 }
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
DATA_INGESTION_URL=https://<data-ingestion-app>.azurewebsites.net
```

Run:
```bash
uvicorn app.main:app --reload --port 8000
# Docs: http://localhost:8000/docs
```

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
