"""
Python Client Simulator

Fetches consumption records from the Data Ingestion Service
and POSTs them to the Data Collection Service as meter readings.
"""
import argparse
from datetime import datetime, timedelta
import os
import sys

import requests

DATA_INGESTION_URL = os.getenv("DATA_INGESTION_URL", "http://localhost:8001")
DATA_COLLECTION_URL = os.getenv("DATA_COLLECTION_URL", "http://localhost:8002")


def main():
    parser = argparse.ArgumentParser(description="SmartGrid meter simulator")
    parser.add_argument("meter_id", type=int, help="ID of the meter to simulate")
    parser.add_argument("--start-date", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", help="End date (YYYY-MM-DD)")
    args = parser.parse_args()

    # Default to 10-day window if no dates provided (~14,400 records)
    start = args.start_date or "2007-01-01"
    if args.end_date:
        end = args.end_date
    else:
        end_dt = datetime.strptime(start, "%Y-%m-%d") + timedelta(days=10)
        end = end_dt.strftime("%Y-%m-%d")

    params = {"start_date": start, "end_date": end}

    print(f"Fetching data from {DATA_INGESTION_URL}/api/v1/consumption ...")
    resp = requests.get(f"{DATA_INGESTION_URL}/api/v1/consumption", params=params, timeout=60)
    resp.raise_for_status()
    records = resp.json()
    print(f"Received {len(records)} records")

    # POST each record to Data Collection Service
    posted = 0
    for record in records:
        payload = {
            "meter_id": args.meter_id,
            "timestamp": record.get("timestamp") or f"{record['date']} {record['time']}",
            "global_active_power": float(record.get("global_active_power", 0)),
            "voltage": float(record.get("voltage", 0)),
            "sub_metering_1": float(record.get("sub_metering_1", 0)),
            "sub_metering_2": float(record.get("sub_metering_2", 0)),
            "sub_metering_3": float(record.get("sub_metering_3", 0)),
        }
        r = requests.post(f"{DATA_COLLECTION_URL}/readings", json=payload, timeout=10)
        r.raise_for_status()
        posted += 1

    print(f"Successfully posted {posted} readings for meter {args.meter_id}")


if __name__ == "__main__":
    main()
