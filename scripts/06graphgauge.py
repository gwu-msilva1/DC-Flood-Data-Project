
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# SECTION 1: Locate project files

ROOT = Path(__file__).resolve().parent.parent

GAUGE_FILE = (
    ROOT / "data" / "processed" / "gauges" /
    "gauge_USGS-01648010_FLOOD_125.csv"
)

EVENTS_FILE = (
    ROOT / "data" / "processed" /
    "flood_events_cleaned.csv"
)

FIGURE_DIR = ROOT / "outputs" / "figures"
FIGURE_DIR.mkdir(parents=True, exist_ok=True)


# SECTION 2: Read gauge measurements

gauge = pd.read_csv(GAUGE_FILE)

gauge["time_utc"] = pd.to_datetime(
    gauge["time_utc"],
    utc=True
)

gauge["gauge_height"] = pd.to_numeric(
    gauge["gauge_height"],
    errors="coerce"
)

gauge = gauge.sort_values("time_utc")


# SECTION 3: Locate the flood event

events = pd.read_csv(EVENTS_FILE)

event = events.loc[
    events["event_id"] == "FLOOD_125"
].iloc[0]

event_start = pd.to_datetime(
    event["begin_utc"], utc=True
)

event_end = pd.to_datetime(
    event["end_utc"], utc=True
)

# Convert both event and station observations
# to local civil time for display.

gauge["time_dc"] = gauge["time_utc"].dt.tz_convert(
    "America/New_York"
)

event_start_dc = event_start.tz_convert(
    "America/New_York"
)

event_end_dc = event_end.tz_convert(
    "America/New_York"
)


# SECTION 4: Create the graph

fig, ax = plt.subplots(figsize=(12, 6))

ax.plot(
    gauge["time_dc"],
    gauge["gauge_height"],
    color="steelblue",
    linewidth=1.5,
    label="Gauge height"
)

# Highlight the reported flood interval.
ax.axvspan(
    event_start_dc,
    event_end_dc,
    color="orange",
    alpha=0.25,
    label="Reported flood interval"
)

ax.set_title(
    "Rock Creek at Joyce Road — Gauge Height\n"
    "Washington, DC | July 19, 2025"
)

ax.set_xlabel(
    "Local time (America/New_York, EDT)"
)

ax.set_ylabel("Gauge height (feet)")

ax.xaxis.set_major_formatter(
    mdates.DateFormatter(
        "%b %d\n%I:%M %p",
        tz=gauge["time_dc"].dt.tz
    )
)

ax.grid(alpha=0.3)

ax.legend()

plt.tight_layout()


# SECTION 5: Save the graph

output_path = (
    FIGURE_DIR /
    "rock_creek_gauge_FLOOD_125.png"
)

plt.savefig(output_path, dpi=300)
plt.show()

print("Graph saved to:", output_path)

print(
    "Minimum gauge height:",
    gauge["gauge_height"].min()
)

print(
    "Maximum gauge height:",
    gauge["gauge_height"].max()
)

print("Graph created successfully!")
