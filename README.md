# Dublin Bikes — Station Usage Analysis

A small end-to-end data science project: collect real-time Dublin Bikes station
data from the public GBFS API, clean it, explore usage patterns in a notebook,
and serve the results in an interactive Streamlit dashboard.

It's intentionally built as a **pipeline of small, separate pieces** rather
than one big script — that's the main thing worth learning from it. Each
stage reads a file the previous stage wrote and doesn't know or care how
that file was produced:

```
scripts/collect_data.py  -->  data/raw/*.csv           (raw snapshots, one row per station per poll)
scripts/clean_data.py    -->  data/processed/*.csv     (one tidy, analysis-ready table)
analysis/*.ipynb         <--  reads data/processed/    (exploration, plots, questions)
dashboard/app.py         <--  reads data/processed/    (interactive version of the same questions)
```

## The data source

This project uses the **GBFS** (General Bikeshare Feed Specification) feed
published for Dublin Bikes by JCDecaux / Smart Dublin — the same open data
that powers things like the TFI Journey Planner:

- Discovery: https://api.cyclocity.fr/contracts/dublin/gbfs/gbfs.json
- Station info (static): https://api.cyclocity.fr/contracts/dublin/gbfs/v2/station_information.json
- Station status (live, refreshes ~every minute): https://api.cyclocity.fr/contracts/dublin/gbfs/v2/station_status.json

**No API key or signup is required** — it's a public JSON feed. That's
unusual (JCDecaux's older "Vélib'-style" API needs a key); GBFS is a
standardized, open format increasingly used by bike-share systems worldwide
specifically so apps like Google Maps and journey planners can integrate
without friction.

The catch: the API only ever gives you the *current* moment. There is no
"give me last week's data" endpoint. This is exactly why `collect_data.py`
exists as a standalone, schedulable script — you have to be the one
snapshotting the present in order to have a past to analyze.

## Project structure

```
dublin-bikes-analysis/
├── scripts/
│   ├── collect_data.py    # polls the API, appends snapshots to data/raw/
│   └── clean_data.py      # merges + cleans data/raw/ -> data/processed/
├── analysis/
│   └── exploratory_analysis.ipynb   # EDA: busiest stations, time patterns, etc.
├── dashboard/
│   └── app.py              # Streamlit dashboard (interactive version of the EDA)
├── data/
│   ├── raw/                # untouched API snapshots (gitignored — you generate these)
│   ├── processed/          # cleaned table used by the notebook & dashboard (gitignored)
│   └── sample/              # a small real sample so the dashboard has something to
│                             # show immediately, without waiting for your own collection
├── requirements.txt
└── .gitignore
```

`data/raw/` and `data/processed/` are gitignored on purpose: this is
*collected*, ever-growing data, not source code, and everyone who clones
this repo can (and should) collect their own. `data/sample/` is the one
exception — a few minutes of real data captured while building this
project, committed so you can see the dashboard populated on the very
first run.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

**1. Collect some data.** A single run grabs one snapshot (useful for
testing); `--loop` keeps polling so you build up real history over time —
this is the step that actually needs to run continuously to be useful:

```bash
# one snapshot, then exit
python scripts/collect_data.py

# poll every 5 minutes, forever (Ctrl+C to stop)
python scripts/collect_data.py --loop --interval 300

# poll every 5 minutes for 3 days, then stop on its own
python scripts/collect_data.py --loop --interval 300 --duration 4320
```

For real usage patterns (commuter rush hours, weekday vs. weekend), let
this run for at least a few days. On Linux/macOS, a cron entry works well;
on Windows, use Task Scheduler (see below). A quick test run of a few
minutes is enough to confirm the pipeline works, but won't show you much
of a "pattern" yet.

### Automating collection on Windows (Task Scheduler)

Rather than `--loop`, on Windows it's more reliable to let Task Scheduler
call `collect_data.py` once every few minutes — that way a single crashed
run doesn't kill collection for the rest of the week, and it keeps running
even across reboots/logins.

`scripts/run_collector_task.ps1` is a small wrapper that does the actual
work: it calls `collect_data.py` and appends its output to
`data/raw/collector.log`, so you have somewhere to look if a scheduled run
ever goes quiet. (It shells out to `cmd.exe` for that redirection
specifically because PowerShell's own `*>>` redirection re-encodes an
external program's output as UTF-16 and garbles it — worth remembering if
you ever build a similar wrapper.)

Task Scheduler itself is pointed at `scripts/run_collector_task.vbs`, not
the `.ps1` directly. That extra layer exists purely to stop a console
window from flashing on screen every 5 minutes: `powershell.exe -WindowStyle
Hidden` still briefly flashes a window on some Windows builds, but
launching it through `WScript.Shell.Run(..., 0, False)` from a `.vbs` is
the reliable way to get a genuinely invisible run every time.

To set it up (adjust the interval as needed):

```powershell
$vbsPath = "C:\path\to\dublin-bikes-analysis\scripts\run_collector_task.vbs"
schtasks /create /tn "DublinBikesCollector" `
  /tr "wscript.exe //B `"$vbsPath`"" `
  /sc MINUTE /mo 5 /f
```

Useful commands once it's created:

```powershell
schtasks /query /tn "DublinBikesCollector" /v /fo LIST   # check status / last result
schtasks /run /tn "DublinBikesCollector"                  # trigger a run right now
schtasks /delete /tn "DublinBikesCollector" /f            # stop and remove it
```

By default the task only runs while you're logged in (no stored
credentials needed). If you want it to run even when logged out, recreate
it with `/ru` and `/rp` (username/password) plus `/it` — see
`schtasks /create /?`.

**2. Clean it** into one analysis-ready table:

```bash
python scripts/clean_data.py
```

**3. Explore it** in the notebook:

```bash
jupyter notebook analysis/exploratory_analysis.ipynb
```

**4. Look at the dashboard:**

```bash
streamlit run dashboard/app.py
```

If you haven't collected any data of your own yet, copy the bundled sample
into place first so the dashboard has something to show:

```bash
# macOS/Linux
cp data/sample/station_status_clean_sample.csv data/processed/station_status_clean.csv
# Windows (PowerShell)
Copy-Item data\sample\station_status_clean_sample.csv data\processed\station_status_clean.csv
```

## What the dashboard shows

- A live map of every station, colored by how full it currently is.
- The busiest stations at each end: stations that run mostly *empty*
  (high demand for bikes) and stations that run mostly *full* (popular
  drop-off points) — both are useful for planning manual rebalancing.
- Network-wide occupancy over time, plus per-station comparisons.
- An hour-of-day × day-of-week heatmap, to spot commuter rush-hour patterns
  once enough history has been collected.

## Findings so far (a full week: Tue Aug 4 – Tue Aug 11, 2026)

The collector has now spanned a full calendar week, giving 87,894
snapshots across 114 stations (771 distinct snapshot times) — roughly 4x
the data behind the original four-weekday findings. The headline: the
collector finally got one genuinely **continuous run — about 46 hours,
from late Friday night (Aug 7, 23:46 UTC) through Sunday evening (Aug 9,
22:04 UTC)**. That happened to land almost entirely on the weekend, which
transformed the weekend picture but — importantly — left the project's
original question about the *weekday* morning rush still unanswered:

- **The weekday morning rush hour is still not visible.** Across every
  weekday collected so far (Tue Aug 4 – Fri Aug 7, plus Mon Aug 10 and
  Tue Aug 11), there are **zero snapshots between roughly 06:00 and 13:00
  UTC (07:00–14:00 local)** — the entire workday morning through early
  afternoon, commute included, is blank on every single weekday. The one
  continuous stretch the collector achieved ran through the weekend
  instead, and then went patchy again from Monday morning onward —
  consistent with the known limitation noted below (Task Scheduler only
  runs while logged in). So the original blind spot from the first four
  days hasn't closed; it just moved out of the way of the weekend.
- **The weekend picture, on the other hand, is now excellent — and shows
  a genuinely different pattern.** Saturday and Sunday each have full
  24-hour coverage (~1,368 samples per hour: all 114 stations × 12 polls).
  Both days show one broad midday trough rather than sharp AM/PM peaks:
  network occupancy sits around 40–41% overnight, drifts down to ~38%
  between roughly 10am and 4pm local, then climbs back to 40–41% by
  evening. That's a leisure-usage signature — a single gentle dip — not
  the two-peak commuter shape the project is ultimately trying to
  capture.
- **Weekday vs. weekend: a tentative but consistent gap.** At the hours
  where both weekday and weekend data actually exist (roughly 00:00–02:00,
  16:00–19:00, and 21:00–23:00 UTC), weekdays run about 2–4 percentage
  points *emptier* than the same hour on Saturday/Sunday — e.g. midnight
  UTC averages ~38.7% on weekdays vs. ~40.6% on weekends. The direction is
  consistent across every overlapping hour, which is a real lead, but
  weekday sample sizes at these hours are thin and none of them touch the
  actual commute window — treat this as suggestive, not confirmed.
- **Station-level findings got more solid, not different.** With ~4x the
  data, the same stations top both ends: Fitzwilliam Square East (0.6%
  avg occupancy) and Eccles Street East (2.0%) remain the clearest demand
  hotspots; Heuston Bridge North and South remain the clearest drop-off
  points (87–93% full). Capacity vs. occupancy correlation firmed up from
  -0.16 to -0.36 — still weak-to-moderate, same conclusion: station
  location plausibly matters more than size.

The honest summary: a full week of wall-clock time has passed, but the
collector has only had one truly gap-free stretch, and it happened to
fall on the weekend. That's a genuinely useful, unplanned result —
Dublin Bikes' weekend usage pattern is now well characterized — but it
means the project's original goal (seeing the weekday commuter rush hour)
still needs one more thing: the collector surviving a full weekday,
overnight through the following evening, without a login/logout gap.

## Notes on design choices

- **Occupancy ratio** (`bikes available ÷ dock capacity`) is used instead of
  raw bike counts throughout, because comparing raw counts across stations
  of very different sizes is misleading — 5 free bikes means something
  different at a 10-dock station than at a 40-dock station.
- Charts use a single blue hue, light→dark, for anything that's a
  *magnitude* (occupancy, demand ranking), and a small fixed-order set of
  distinct hues only where something is a genuine *category* (comparing a
  handful of named stations on one chart) — so color always tells you
  whether you're looking at "how much" or "which one."
- One CSV per UTC day in `data/raw/` (rather than one giant ever-growing
  file) keeps individual files small enough to open and skim directly.

## Ideas for extending this

- Join in a weather API and check whether rain suppresses ridership.
- Fit a simple model to predict next-hour occupancy for a given station.
- Add a "stations at risk of going empty/full in the next hour" alert view.
