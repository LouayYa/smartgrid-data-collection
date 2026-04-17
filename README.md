# SmartGrid Insights — Data Collection Service

> **Service 3 of 5** | CMP404 Spring 2026 · Team 5 | Developed by **Louy Abbas** · AUS

## Overview

Receives and stores smart meter readings from the Python Client Simulator, exposes a simulation trigger endpoint, and serves collected readings to the Data Analysis Service. Deployed as an Azure App Service with its own dedicated Azure SQL Database.

**Stack:** FastAPI · SQLAlchemy · PyMySQL · Pydantic · Azure App Service · GitHub Actions

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

Base URL: `https://<data-collection-app>.azurewebsites.net`

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

**Table: `readings`** (Azure SQL — Data Collection DB)

| Column | Type | Description |
|---|---|---|
| `reading_id` | INT PK | Auto-increment |
| `meter_id` | INT | References a registered meter |
| `timestamp` | DATETIME | Reading timestamp |
| `global_active_power` | FLOAT | Total active power (kW) |
| `voltage` | FLOAT | Voltage (V) |
| `sub_metering_1/2/3` | FLOAT | Kitchen / Laundry / Water heater (Wh) |

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
DB_HOST=<your-db-host>
DB_PORT=3306
DB_NAME=data_collection_db
DB_USER=<your-db-user>
DB_PASSWORD=<your-db-password>
DATA_INGESTION_URL=https://<data-ingestion-app>.azurewebsites.net
```

Run:
```bash
uvicorn app.main:app --reload --port 8000
# Docs: http://localhost:8000/docs
```

---

## CI/CD — Deployment to Azure App Service

The service is deployed to Azure App Service via **GitHub Actions**, configured through **Azure Deployment Center** — no manual workflow setup required.

**How it was set up:**
1. In the Azure Portal, navigate to the App Service → **Deployment Center**
2. Under **Source**, select **GitHub** and authorize Azure to access your account
3. Select the repository (`smartgrid-data-collection`) and branch (`main`)
4. Azure automatically generates and commits a GitHub Actions workflow file to `.github/workflows/`

From that point on, every push to `main` triggers the workflow — it builds the Python app and deploys it to the App Service automatically.

App Service environment variables (DB credentials, `DATA_INGESTION_URL`) are configured under **App Service → Settings → Configuration** in the Azure Portal, not committed to the repo.

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
