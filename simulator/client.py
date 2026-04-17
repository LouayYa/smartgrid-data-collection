"""
Python Client Simulator

Fetches consumption records from the Data Ingestion Service
and POSTs them to the Data Collection Service as meter readings.
"""
import argparse
from datetime import datetime, timedelta
import os

import requests

DATA_INGESTION_URL = os.getenv("DATA_INGESTION_URL", "http://localhost:8001")
DATA_COLLECTION_URL = os.getenv("DATA_COLLECTION_URL", "http://localhost:8002")


def parse_ingestion_timestamp(date_str: str, time_str: str) -> str:
    """Convert ingestion service's d/m/yy or d/m/yyyy + HH:MM:SS into ISO format."""
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            d = datetime.strptime(date_str.strip(), fmt)
            t = datetime.strptime(time_str.strip(), "%H:%M:%S").time()
            return datetime.combine(d.date(), t).isoformat()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date: {date_str!r}")


def main():
    parser = argparse.ArgumentParser(description="SmartGrid meter simulator")
    parser.add_argument("meter_id", type=int, help="ID of the meter to simulate")
    parser.add_argument("--start-date", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", help="End date (YYYY-MM-DD)")
    args = parser.parse_args()

    # Default to 10-day window if no dates provided (~14,400 records)
    start = args.start_date or "2007-01-01"
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    if args.end_date:
        end_dt = datetime.strptime(args.end_date, "%Y-%m-%d")
    else:
        end_dt = start_dt + timedelta(days=10)

    # Ingestion service expects d/m/yyyy format
    params = {
        "start_date": start_dt.strftime("%-d/%-m/%Y") if os.name != "nt" else f"{start_dt.day}/{start_dt.month}/{start_dt.year}",
        "end_date": end_dt.strftime("%-d/%-m/%Y") if os.name != "nt" else f"{end_dt.day}/{end_dt.month}/{end_dt.year}",
        "limit": 100000,
    }

    print(f"Fetching data from {DATA_INGESTION_URL}/api/v1/consumption with {params}")
    resp = requests.get(f"{DATA_INGESTION_URL}/api/v1/consumption", params=params, timeout=240)
    resp.raise_for_status()
    records = resp.json()
    print(f"Received {len(records)} records")

    payloads = []
    for record in records:
        try:
            timestamp = parse_ingestion_timestamp(record["Date"], record["Time"])
        except (KeyError, ValueError) as e:
            print(f"Skipping malformed record: {e}")
            continue

        payloads.append({
            "meter_id": args.meter_id,
            "timestamp": timestamp,
            "global_active_power": float(record.get("Global_active_power") or 0),
            "voltage": float(record.get("Voltage") or 0),
            "sub_metering_1": float(record.get("Sub_metering_1") or 0),
            "sub_metering_2": float(record.get("Sub_metering_2") or 0),
            "sub_metering_3": float(record.get("Sub_metering_3") or 0),
        })

    BATCH_SIZE = 1000
    posted = 0
    session = requests.Session()
    for i in range(0, len(payloads), BATCH_SIZE):
        batch = payloads[i : i + BATCH_SIZE]
        r = session.post(f"{DATA_COLLECTION_URL}/readings/bulk", json=batch, timeout=60)
        r.raise_for_status()
        posted += len(batch)
        print(f"Posted {posted}/{len(payloads)}")

    print(f"Successfully posted {posted} readings for meter {args.meter_id}")


if __name__ == "__main__":
    main()
