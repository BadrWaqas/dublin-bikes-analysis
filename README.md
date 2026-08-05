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
