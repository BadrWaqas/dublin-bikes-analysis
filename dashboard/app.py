"""
Streamlit dashboard for exploring Dublin Bikes station usage patterns.

Streamlit re-runs this whole script top-to-bottom every time a user touches
a widget (a dropdown, a slider). That sounds wasteful, but it's what makes
the "just write plain Python, get a web app" model work -- there's no
separate client/server state to manage by hand. The one thing you *do* have
to manage yourself is expensive work (like loading a CSV): `@st.cache_data`
tells Streamlit "only re-run this function if its inputs changed", so
re-running the script on every click doesn't mean re-reading the file every
click.

Run with:
    streamlit run dashboard/app.py
"""

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FULL_DATA_PATH = PROJECT_ROOT / "data" / "processed" / "station_status_clean.csv"
PUBLISHED_DATA_PATH = PROJECT_ROOT / "data" / "published" / "station_status_clean.csv.gz"
SAMPLE_DATA_PATH = PROJECT_ROOT / "data" / "sample" / "station_status_clean_sample.csv"

# Prefer data you've collected yourself (local runs). Otherwise use the
# committed snapshot of the original collection window (compressed), so a
# fresh clone or a hosted deploy (e.g. Streamlit Community Cloud) shows the
# full analysis. The tiny sample is a last resort.
if FULL_DATA_PATH.exists():
    DATA_PATH = FULL_DATA_PATH
elif PUBLISHED_DATA_PATH.exists():
    DATA_PATH = PUBLISHED_DATA_PATH
else:
    DATA_PATH = SAMPLE_DATA_PATH
USING_SAMPLE = DATA_PATH == SAMPLE_DATA_PATH

# Reference palette (see dataviz notes in README): fixed-order categorical
# hues, and a single blue hue ramp for magnitude/sequential encodings. Fixed
# order matters more than the exact hues -- it means "station A" gets the
# same color every time it appears, instead of colors reshuffling whenever
# the station list changes.
CATEGORICAL_PALETTE = [
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100",
    "#e87ba4", "#008300", "#4a3aa7", "#e34948",
]
SEQUENTIAL_BLUE = "Blues"

DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

st.set_page_config(page_title="Dublin Bikes Usage Patterns", page_icon="🚲", layout="wide")


@st.cache_data(ttl=60)
def load_data() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH, parse_dates=["query_time"])
    df["date"] = pd.to_datetime(df["date"])
    df["day_of_week"] = pd.Categorical(df["day_of_week"], categories=DAY_ORDER, ordered=True)
    return df


st.title("🚲 Dublin Bikes — Station Usage Patterns")
st.caption(
    "Data collected from the public Dublin Bikes GBFS feed "
    "(api.cyclocity.fr/contracts/dublin/gbfs). No API key required."
)

if not DATA_PATH.exists():
    st.error(
        "No processed data found yet.\n\n"
        "Run these first, from the project root:\n\n"
        "```\npython scripts/collect_data.py\npython scripts/clean_data.py\n```"
    )
    st.stop()

if USING_SAMPLE:
    st.info(
        "Showing a small bundled sample of the data. Run the collector locally "
        "for the full dataset."
    )

df = load_data()

if df.empty:
    st.warning("The processed dataset is empty. Collect some data first.")
    st.stop()

# --- Sidebar filters -------------------------------------------------------
st.sidebar.header("Filters")

min_date, max_date = df["date"].min().date(), df["date"].max().date()
if min_date == max_date:
    st.sidebar.caption(f"All data is from {min_date} (collection window is short so far).")
    date_range = (min_date, max_date)
else:
    date_range = st.sidebar.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
    if isinstance(date_range, tuple) and len(date_range) == 1:
        date_range = (date_range[0], date_range[0])

station_names = sorted(df["name"].dropna().unique())
selected_stations = st.sidebar.multiselect(
    "Focus on specific stations (optional)", station_names, default=[]
)

mask = (df["date"].dt.date >= date_range[0]) & (df["date"].dt.date <= date_range[1])
filtered = df[mask]
if selected_stations:
    filtered = filtered[filtered["name"].isin(selected_stations)]

if filtered.empty:
    st.warning("No rows match the current filters.")
    st.stop()

# --- KPI row ----------------------------------------------------------------
latest_time = filtered["query_time"].max()
latest = filtered[filtered["query_time"] == latest_time]

col1, col2, col3, col4 = st.columns(4)
col1.metric("Stations in view", f"{filtered['station_id'].nunique()}")
col2.metric("Bikes available (latest snapshot)", f"{int(latest['num_bikes_available'].sum()):,}")
col3.metric("Avg occupancy (latest snapshot)", f"{latest['occupancy_ratio'].mean() * 100:.0f}%")
col4.metric("Snapshots collected", f"{filtered['query_time'].nunique():,}")

st.divider()

# --- Station map --------------------------------------------------------
st.subheader("Station map — current bike availability")
st.caption(
    "Color encodes occupancy (bikes available ÷ dock capacity) at the most recent "
    "snapshot in the selected range: dark = nearly full, light = nearly empty. "
    "One hue, light-to-dark, because this is a magnitude, not a category."
)

map_fig = px.scatter_map(
    latest,
    lat="lat",
    lon="lon",
    color="occupancy_ratio",
    size="capacity",
    size_max=18,
    color_continuous_scale=SEQUENTIAL_BLUE,
    range_color=(0, 1),
    hover_name="name",
    hover_data={"num_bikes_available": True, "capacity": True, "occupancy_ratio": ":.0%", "lat": False, "lon": False},
    zoom=12,
    center={"lat": float(latest["lat"].mean()), "lon": float(latest["lon"].mean())},
    height=500,
)
# CARTO's basemap tiles load reliably from hosted apps; the default
# OpenStreetMap tile servers can refuse requests and leave a blank map.
map_fig.update_layout(map_style="carto-positron", margin=dict(l=0, r=0, t=0, b=0))
map_fig.update_coloraxes(colorbar_title="Occupancy")
st.plotly_chart(map_fig, width='stretch')

st.divider()

# --- Busiest vs quietest stations -------------------------------------------
st.subheader("Which stations see the most demand?")
st.caption(
    "'Demand' here is read from low average occupancy — a station that sits mostly "
    "empty is one where riders take bikes out faster than docks refill (e.g. downhill "
    "commuter routes), while a mostly-full station is a popular drop-off point. Both "
    "matter for rebalancing trucks, so we show both ends."
)

station_avg = (
    filtered.groupby(["station_id", "name"], as_index=False)
    .agg(avg_occupancy=("occupancy_ratio", "mean"), capacity=("capacity", "first"))
)

top_n = st.slider("Number of stations to show at each end", 5, 20, 10)

left, right = st.columns(2)
with left:
    emptiest = station_avg.nsmallest(top_n, "avg_occupancy").sort_values("avg_occupancy")
    fig = px.bar(
        emptiest, x="avg_occupancy", y="name", orientation="h",
        color="avg_occupancy", color_continuous_scale=SEQUENTIAL_BLUE, range_color=(0, 1),
        labels={"avg_occupancy": "Avg occupancy", "name": ""},
        title="Most in-demand (lowest avg. occupancy)",
    )
    fig.update_layout(coloraxis_showscale=False, xaxis_tickformat=".0%")
    st.plotly_chart(fig, width='stretch')

with right:
    fullest = station_avg.nlargest(top_n, "avg_occupancy").sort_values("avg_occupancy")
    fig = px.bar(
        fullest, x="avg_occupancy", y="name", orientation="h",
        color="avg_occupancy", color_continuous_scale=SEQUENTIAL_BLUE, range_color=(0, 1),
        labels={"avg_occupancy": "Avg occupancy", "name": ""},
        title="Most popular drop-off (highest avg. occupancy)",
    )
    fig.update_layout(coloraxis_showscale=False, xaxis_tickformat=".0%")
    st.plotly_chart(fig, width='stretch')

st.divider()

# --- Time patterns -----------------------------------------------------
st.subheader("Occupancy over time")

n_days = filtered["date"].nunique()
if n_days < 2:
    st.info(
        f"Only {n_days} day of data collected so far, so hour/day-of-week patterns "
        "won't be meaningful yet. Leave `collect_data.py` running for a few days "
        "(e.g. via cron or Windows Task Scheduler) to see real commuter patterns emerge."
    )

network_avg = filtered.groupby("query_time", as_index=False)["occupancy_ratio"].mean()

# The collector had downtime (e.g. the PC asleep). Break the line wherever
# consecutive snapshots are more than 30 minutes apart, so gaps show as gaps
# instead of straight lines that invent data that was never collected.
gap = network_avg["query_time"].diff() > pd.Timedelta(minutes=30)
if gap.any():
    breaks = network_avg.loc[gap, ["query_time"]].copy()
    breaks["query_time"] -= pd.Timedelta(seconds=1)
    breaks["occupancy_ratio"] = None
    network_avg = pd.concat([network_avg, breaks]).sort_values("query_time")
    st.caption("Breaks in the line are periods when the collector wasn't running.")

line_fig = go.Figure()
line_fig.add_trace(go.Scatter(
    x=network_avg["query_time"], y=network_avg["occupancy_ratio"],
    mode="lines", line=dict(color=CATEGORICAL_PALETTE[0], width=2),
    name="Network average", hovertemplate="%{x}<br>Occupancy: %{y:.0%}<extra></extra>",
))
line_fig.update_layout(
    yaxis_tickformat=".0%", yaxis_title="Avg occupancy", xaxis_title="",
    height=350, showlegend=False,
)
st.plotly_chart(line_fig, width='stretch')

if selected_stations:
    st.caption("Selected stations over time:")
    per_station = filtered.groupby(["query_time", "name"], as_index=False)["occupancy_ratio"].mean()
    fig = px.line(
        per_station, x="query_time", y="occupancy_ratio", color="name",
        color_discrete_sequence=CATEGORICAL_PALETTE,
        labels={"occupancy_ratio": "Occupancy", "query_time": "", "name": "Station"},
    )
    fig.update_layout(yaxis_tickformat=".0%", height=350)
    st.plotly_chart(fig, width='stretch')

# --- Hour x day-of-week heatmap ---------------------------------------------
st.subheader("When is the network busiest?")
st.caption(
    "Average occupancy by hour of day and day of week — darker means more bikes docked "
    "(less availability). The colour scale is stretched to the range in the data so "
    "differences are visible; blank cells are hours with no data collected."
)

heatmap_data = (
    filtered.groupby(["day_of_week", "hour"], as_index=False, observed=False)["occupancy_ratio"]
    .mean()
    .pivot(index="day_of_week", columns="hour", values="occupancy_ratio")
    .reindex(DAY_ORDER)
)
heat_fig = px.imshow(
    heatmap_data,
    color_continuous_scale=SEQUENTIAL_BLUE,
    # Network averages sit in a narrow band (~30-45%), so a fixed 0-100% scale
    # paints every cell the same pale blue. Fit the scale to the data instead.
    zmin=float(heatmap_data.min().min()) if heatmap_data.notna().any().any() else 0,
    zmax=float(heatmap_data.max().max()) if heatmap_data.notna().any().any() else 1,
    labels=dict(x="Hour of day", y="", color="Occupancy"),
    aspect="auto",
)
heat_fig.update_layout(height=350, coloraxis_colorbar_tickformat=".0%")
st.plotly_chart(heat_fig, width='stretch')

with st.expander("View underlying data"):
    st.dataframe(filtered.sort_values("query_time", ascending=False), width='stretch')

