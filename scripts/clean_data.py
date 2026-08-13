"""
Turns the raw GBFS snapshots in data/raw/ into one tidy table ready for
analysis, saved to data/processed/station_status_clean.csv.

Why not analyze data/raw/ directly? A few reasons this step exists as its
own script instead of living inside the notebook:

1. REPRODUCIBILITY. "Cleaning" involves judgment calls (what counts as a
   duplicate? what do we do with a station that's offline?). Writing those
   decisions once, in one script, means every notebook or dashboard that
   reads data/processed/ sees the exact same answer -- instead of each one
   re-implementing (and maybe subtly disagreeing on) the same logic.
2. SEPARATION OF CONCERNS. Raw data is allowed to be messy -- it's a direct
   record of what the API returned. Processed data is not allowed to be
   messy. Keeping them as two separate files (not two states of the same
   file) means you can always regenerate "clean" from "raw" if you change
   your mind about a cleaning rule, without re-collecting anything.
3. It's the same reason spreadsheets get you in trouble: if cleaning steps
   only exist as manual actions you did once in a notebook, nobody
   (including future-you) can tell what was done or redo it on new data.

Cleaning steps applied here:
- Combine every data/raw/station_status_*.csv (one per day) into one table.
- Join in the static station info (name, lat/lon, capacity) by station_id.
- Drop rows for stations that were offline (is_installed == False), since
  a station that isn't installed doesn't tell us anything about usage.
- Derive an `occupancy_ratio` (bikes available / capacity) -- comparing
  raw bike counts across stations of different sizes is misleading, e.g.
  5 bikes free means something different at a 10-dock station than a
  40-dock station.
- Derive calendar features (date, hour, day_of_week) used throughout the
  analysis and dashboard for "what time of day/week is busiest" questions.

Usage:
    python clean_data.py
"""

from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
OUTPUT_PATH = PROCESSED_DIR / "station_status_clean.csv"

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def load_raw_status() -> pd.DataFrame:
    status_files = sorted(RAW_DIR.glob("station_status_*.csv"))
    if not status_files:
        raise FileNotFoundError(
            f"No station_status_*.csv files found in {RAW_DIR}. "
            "Run scripts/collect_data.py first to gather some data."
        )
    frames = [pd.read_csv(f, parse_dates=["query_time"]) for f in status_files]
    return pd.concat(frames, ignore_index=True)


def load_station_info() -> pd.DataFrame:
    info_path = RAW_DIR / "station_information.csv"
    if not info_path.exists():
        raise FileNotFoundError(f"{info_path} not found. Run scripts/collect_data.py first.")
    return pd.read_csv(info_path)


def clean(status: pd.DataFrame, info: pd.DataFrame) -> pd.DataFrame:
    df = status.merge(info, on="station_id", how="left", validate="many_to_one")

    # A station that isn't installed can't be "busy" or "quiet" -- it's just
    # absent from the network (temporarily removed, under maintenance, etc.).
    df = df[df["is_installed"] == True].copy()  # noqa: E712 (pandas bool column)

    # Duplicate polls can happen if the collector overlaps with itself, or a
    # station reports the same query_time twice within one snapshot.
    df = df.drop_duplicates(subset=["query_time", "station_id"])

    df["occupancy_ratio"] = (df["num_bikes_available"] / df["capacity"]).clip(0, 1)

    # query_time is UTC. Convert to Dublin local time before deriving
    # calendar features -- otherwise "hour of day" is off by an hour during
    # BST (late Mar-late Oct) and rush-hour patterns get mislabeled.
    local_time = df["query_time"].dt.tz_convert("Europe/Dublin")
    df["date"] = local_time.dt.date
    df["hour"] = local_time.dt.hour
    df["day_of_week"] = local_time.dt.dayofweek.map(dict(enumerate(DAY_NAMES)))

    columns = [
        "query_time", "date", "hour", "day_of_week",
        "station_id", "name", "lat", "lon", "capacity",
        "num_bikes_available", "num_docks_available", "occupancy_ratio",
        "is_renting", "is_returning",
    ]
    return df[columns].sort_values(["station_id", "query_time"]).reset_index(drop=True)


def main() -> None:
    status = load_raw_status()
    info = load_station_info()
    clean_df = clean(status, info)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    clean_df.to_csv(OUTPUT_PATH, index=False)

    n_stations = clean_df["station_id"].nunique()
    n_snapshots = clean_df["query_time"].nunique()
    print(f"Wrote {len(clean_df):,} rows -> {OUTPUT_PATH}")
    print(f"({n_stations} stations x {n_snapshots} snapshot times)")


if __name__ == "__main__":
    main()
