"""
Take ONE snapshot of the Dublin Bikes feed and append it, cleaned, to the
published dataset. Built to run unattended on GitHub Actions
(.github/workflows/collect.yml) so collection no longer depends on a PC
being switched on -- the gaps in the original collection window came from
exactly that.

Why a separate script instead of re-running collect_data.py + clean_data.py?
Those two rebuild everything from data/raw/, which a fresh CI checkout
doesn't have (raw snapshots aren't committed). This script reuses their
functions on a single snapshot and appends the result.

Storage layout:
- data/published/station_status_clean.csv.gz   the original collection window (never rewritten)
- data/published/daily/YYYY-MM-DD.csv          one plain-text file per day, appended to

Plain-text daily files on purpose: each run only adds ~114 lines, and git
stores appended text as tiny deltas. Rewriting one big .gz every 30 minutes
would add a full copy of the file to the repo history on every run.

Usage:
    python scripts/ci_append.py
"""

import sys
from pathlib import Path

import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import clean_data  # noqa: E402  (needs the sys.path tweak above)
import collect_data  # noqa: E402

DAILY_DIR = SCRIPTS_DIR.parent / "data" / "published" / "daily"


def main() -> None:
    # 1. Fetch: static station info + one status snapshot, into data/raw/.
    collect_data.save_station_information()
    collect_data.collect_once()

    # 2. Clean with exactly the same rules as the local pipeline.
    snapshot = clean_data.clean(clean_data.load_raw_status(), clean_data.load_station_info())
    if snapshot.empty:
        print("Snapshot had no installed stations; nothing to append.")
        return

    # 3. Append to today's file (Dublin local date, matching the `date` column).
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    day = str(snapshot["date"].iloc[0])
    out = DAILY_DIR / f"{day}.csv"

    if out.exists():
        # Skip if this exact snapshot time is already saved (e.g. a re-run).
        seen = set(pd.read_csv(out, usecols=["query_time"])["query_time"].astype(str))
        snapshot = snapshot[~snapshot["query_time"].astype(str).isin(seen)]
        if snapshot.empty:
            print("Snapshot already saved; nothing to append.")
            return

    snapshot.to_csv(out, mode="a", header=not out.exists(), index=False)
    print(f"Appended {len(snapshot)} rows -> data/published/daily/{out.name}")


if __name__ == "__main__":
    main()
