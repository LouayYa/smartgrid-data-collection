# SmartGrid Insights — Data Collection Service

> **Service 3 of 5** | CMP404 Spring 2026 · Team 5 | Developed by **Louy Abbas** · AUS

## Overview

One of five independently deployed microservices behind SmartGrid Insights, a system that ingests, stores, and analyzes 260K+ smart meter readings end to end. This service owns the write path, which is **event-driven**: every reading — whether it arrives via the REST API, the simulation endpoint, or the standalone simulator client — is published as a JSON event to the **`meter-readings` Kafka topic** (keyed by `meter_id`, so per-meter ordering is preserved). A dedicated consumer worker ([`app/consumer.py`](app/consumer.py)) is the *single* component that persists readings to PostgreSQL: it validates each event against the same Pydantic schema the API uses, writes in batches, and commits Kafka offsets only after the database transaction succeeds (at-least-once delivery).

Originally deployed on Azure App Service with Azure SQL; the database layer has since been migrated to **PostgreSQL**, and the service carries a **pytest** suite covering its API surface and the consumer's message handling against an isolated SQLite test database and a fake publisher — no live infrastructure required to run tests locally or in CI.

**Stack:** FastAPI · Kafka (confluent-kafka) · SQLAlchemy · PostgreSQL (psycopg2) · Pydantic · pytest · Docker · GitHub Actions · Azure App Service (deploy-on-demand)

---

## Data Flow

```
Client Interface
      │
      ├──► POST /simulate/{meter_id} ── GET /consumption (Data Ingestion Service)
      │            │
      │            └──► publishes readings ──► [ meter-readings topic (Kafka) ]
      │                                                     │
      │                       app/consumer.py  ◄────────────┘
      │                       (validates + batch-inserts — the only DB writer)
      │                              │
      │                              ▼
      │                        PostgreSQL (readings)
      │
      └──► Data Analysis Service  ──► queries this service via GET /readings
```

`POST /readings` and `POST /readings/bulk` follow the same path: they validate and publish to `meter-readings`, returning `202 Accepted` — the consumer persists asynchronously. A standalone simulator client ([`simulator/client.py`](simulator/client.py)) plays the role of a real smart meter and produces directly to the Kafka topic.

---

## API Endpoints

Base URL: `http://localhost:8002` (local dev — the Azure deployment has been decommissioned; see [CI/CD](#cicd))

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/readings` | Publish a single reading to Kafka (`202 Accepted`) |
| `POST` | `/readings/bulk` | Publish a batch of readings to Kafka (`202 Accepted`) |
| `GET` | `/readings` | Get readings — optional `meter_id`, `start_date`, `end_date` (`YYYY-MM-DD`, both inclusive) filters |
| `GET` | `/readings/{id}` | Get a specific reading |
| `DELETE` | `/readings/{id}` | Delete a reading |
| `DELETE` | `/readings/by-meter/{meter_id}` | Delete all readings for a meter |
| `DELETE` | `/readings` | Delete all readings |
| `POST` | `/simulate/{meter_id}` | Replay historical data from the Data Ingestion Service as reading events for this meter — optional `start_date`/`end_date` body fields (defaults to a 10-day window). Returns `202` once all events are acknowledged by the broker; the consumer persists them. |

**Example — trigger simulation:**
```http
POST /simulate/3
{ "start_date": "2007-01-01", "end_date": "2007-01-08" }
```
```json
{ "meter_id": 3, "status": "simulation_published", "records_published": 10080 }
```

If the broker is unreachable or any event fails delivery, write endpoints return `503` — nothing is silently dropped.

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

Schema is managed by **Alembic migrations** ([`alembic/versions/`](alembic/versions/)) — the container entrypoint runs `alembic upgrade head` before serving. Migration `0002` adds a composite `(meter_id, timestamp)` index for the hot query path (meter + date-range filters). The SQLite dev/test fallback still uses `create_all()` for convenience.

---

## Testing

The service ships with a `pytest` suite in [`tests/`](tests/) covering:

- **Write endpoints** — asserting that `POST /readings` and `/readings/bulk` publish validated events (captured by a fake publisher injected via FastAPI dependency override) rather than writing to the DB, plus input-validation rejections (`tests/test_readings.py`)
- **Simulation triggering** — mocking the outbound call to the Data Ingestion Service and asserting readings are correctly parsed and published, including malformed-record skipping (`tests/test_simulate.py`)
- **Consumer message handling** — validating/deserializing Kafka messages (valid, malformed JSON, schema violations) and batch persistence semantics (`tests/test_consumer.py`)

Tests run against an isolated, disposable **SQLite** database and an in-memory fake publisher (`tests/conftest.py`), not real PostgreSQL or Kafka — so they're fast, deterministic, and require no external services or credentials to run.

```bash
pip install pytest pytest-cov httpx
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
KAFKA_BOOTSTRAP_SERVERS=localhost:9094   # host-exposed listener from the umbrella docker-compose
```
Without `DATABASE_URL`, the service falls back to a local SQLite file — handy for a quick look without Postgres.

Run the API and the consumer worker (two processes):
```bash
uvicorn app.main:app --reload --port 8002
python -m app.consumer
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
