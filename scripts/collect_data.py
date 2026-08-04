"""
Collects real-time Dublin Bikes station data from the public GBFS feed
(General Bikeshare Feed Specification) published by JCDecaux/Smart Dublin.

No API key is needed for this feed -- it's the same open data source that
powers apps like the TFI Journey Planner.

Two kinds of data exist in GBFS, and we treat them differently on disk:

- STATIC data (station_information): id, name, lat/lon, capacity. This
  barely ever changes, so we just overwrite one file with the latest copy.
- DYNAMIC data (station_status): bikes available, docks available, etc.
  This changes every minute, so we APPEND a timestamped row per station
  every time the script runs, building up a time series over days/weeks.

Why a separate "collect" script at all, instead of pulling data straight
into the notebook? Two reasons:
1. The API only gives you the *current* moment -- there's no "history"
   endpoint. If you don't save snapshots yourself, you can never look at
   yesterday's rush hour again. Collection has to happen continuously,
   independently of when you happen to be doing analysis.
2. Separating "get the data" from "analyze the data" means you can run
   this on a schedule (cron, Windows Task Scheduler, a small server) and
   let it collect for days, while the analysis code stays untouched.

Usage:
    python collect_data.py                  # take a single snapshot and exit
    python collect_data.py --loop            # keep polling forever (Ctrl+C to stop)
    python collect_data.py --loop --interval 120 --duration 60
        (poll every 120s, stop after ~60 minutes)
"""

import argparse
import csv
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

GBFS_ROOT = "https://api.cyclocity.fr/contracts/dublin/gbfs/v2"
STATION_INFO_URL = f"{GBFS_ROOT}/station_information.json"
STATION_STATUS_URL = f"{GBFS_ROOT}/station_status.json"

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
STATION_INFO_PATH = DATA_DIR / "station_information.csv"

STATUS_FIELDS = [
    "query_time",
    "station_id",
    "num_bikes_available",
    "num_docks_available",
    "num_bikes_disabled",
    "num_docks_disabled",
    "is_installed",
    "is_renting",
    "is_returning",
    "last_reported",
]

INFO_FIELDS = ["station_id", "name", "lat", "lon", "address", "capacity"]


def fetch_json(url: str) -> dict:
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    return response.json()


def save_station_information() -> None:
    """Overwrite the static station reference table with the latest copy."""
    payload = fetch_json(STATION_INFO_URL)
    stations = payload["data"]["stations"]

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATION_INFO_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=INFO_FIELDS)
        writer.writeheader()
        for s in stations:
            writer.writerow({k: s.get(k) for k in INFO_FIELDS})

    print(f"[{now_iso()}] station_information.csv refreshed ({len(stations)} stations)")


def status_file_for_today() -> Path:
    """One CSV per UTC day keeps individual files small and easy to skim,
    instead of one ever-growing file you can barely open in a text editor."""
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return DATA_DIR / f"station_status_{day}.csv"

def collect_once() -> int:
    payload = fetch_json(STATION_STATUS_URL)
    stations = payload["data"]["stations"]
    query_time = now_iso()

    path = status_file_for_today()
    file_exists = path.exists()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=STATUS_FIELDS)
        if not file_exists:
            writer.writeheader()
        for s in stations:
            row = {k: s.get(k) for k in STATUS_FIELDS}
            row["query_time"] = query_time
            writer.writerow(row)

    print(f"[{query_time}] collected {len(stations)} station snapshots -> {path.name}")
    return len(stations)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loop", action="store_true", help="keep polling instead of running once")
    parser.add_argument("--interval", type=int, default=60, help="seconds between polls when looping (default: 60)")
    parser.add_argument("--duration", type=int, default=None, help="stop looping after this many minutes (default: run forever)")
    args = parser.parse_args()

    save_station_information()

    if not args.loop:
        collect_once()
        return

    start = time.monotonic()
    stop_after = args.duration * 60 if args.duration else None
    try:
        while True:
            collect_once()
            if stop_after and (time.monotonic() - start) >= stop_after:
                print("Duration reached, stopping.")
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
