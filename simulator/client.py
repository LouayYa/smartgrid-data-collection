"""
Python Client Simulator

Fetches consumption records from the Data Ingestion Service and streams them
to the `meter-readings` Kafka topic as meter readings — the same path a real
smart meter would use. The Data Collection consumer persists them.

Requires KAFKA_BOOTSTRAP_SERVERS to point at the broker (default
localhost:9094, the host-exposed listener from docker-compose.yml).
"""
import argparse
import json
import os
from datetime import datetime, timedelta

import requests
from confluent_kafka import Producer

DATA_INGESTION_URL = os.getenv("DATA_INGESTION_URL", "http://localhost:8001")
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9094")
READINGS_TOPIC = os.getenv("KAFKA_READINGS_TOPIC", "meter-readings")


def parse_ingestion_timestamp(date_str: str, time_str: str) -> str:
    """Convert the ingestion service's date + HH:MM:SS into an ISO timestamp."""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
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

    params = {
        "start_date": start_dt.strftime("%Y-%m-%d"),
        "end_date": end_dt.strftime("%Y-%m-%d"),
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

    producer = Producer({
        "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
        "acks": "all",
        "enable.idempotence": True,
    })

    delivered = 0
    failed = 0

    def on_delivery(err, msg):
        nonlocal delivered, failed
        if err is None:
            delivered += 1
        else:
            failed += 1
            print(f"Delivery failed: {err}")

    print(f"Producing {len(payloads)} readings to {READINGS_TOPIC} on {KAFKA_BOOTSTRAP_SERVERS}")
    for payload in payloads:
        while True:
            try:
                producer.produce(
                    READINGS_TOPIC,
                    key=str(args.meter_id),
                    value=json.dumps(payload),
                    on_delivery=on_delivery,
                )
                break
            except BufferError:
                producer.poll(1)
        producer.poll(0)
        if delivered and delivered % 5000 == 0:
            print(f"Delivered {delivered}/{len(payloads)}")

    producer.flush(60)
    print(f"Done: {delivered} delivered, {failed} failed for meter {args.meter_id}")


if __name__ == "__main__":
    main()
