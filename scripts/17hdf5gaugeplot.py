
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np

from hdf5_functions import (
    get_gauge_data,
    get_flood_event
)


# SECTION 1: Choose a station and event

STATION_ID = "01648010"
EVENT_ID = "FLOOD_125"

STATION_NAME = "Rock Creek at Joyce Road"


# SECTION 2: Retrieve data from HDF5

gauge, metadata = get_gauge_data(
    STATION_ID,
    EVENT_ID
)

event = get_flood_event(EVENT_ID)

print("Station:", STATION_NAME)
print("Event:", EVENT_ID)
print("Gauge observations:", len(gauge))


# SECTION 3: Read flood-event timestamps

event_start = pd.to_datetime(
    event["begin_utc"], utc=True
)

event_end = pd.to_datetime(
    event["end_utc"], utc=True
)

# The stored event UTC values already reflect
# the instructor's fixed EST (UTC-5) rule.

event_start_dc = event_start.tz_convert(
    "America/New_York"
)

event_end_dc = event_end.tz_convert(
    "America/New_York"
)


# SECTION 4: Identify observation gaps

gauge = gauge.sort_values("time_utc").copy()

time_differences = (
    gauge["time_utc"]
    .diff()
    .dt.total_seconds() / 60
)

typical_interval = (
    time_differences.dropna().mode().iloc[0]
    if time_differences.notna().any()
    else np.nan
)

# Insert a break in the line when there is
# a substantial gap between measurements.
gauge["plot_height"] = gauge["gauge_height"].copy()

if pd.notna(typical_interval):
    gap_starts = (
        time_differences > 1.5 * typical_interval
    )

    # Mark the first point following a gap.
    # A later segment will start with that observation.
    # This avoids visually connecting both sides.
    gap_indices = gauge.index[gap_starts].tolist()
else:
    gap_indices = []


# SECTION 5: Create the water-level graph

fig, ax = plt.subplots(figsize=(12, 6))

# Plot continuous segments separately so genuine
# time gaps aren't connected by a misleading line.
segments = np.split(
    np.arange(len(gauge)),
    gap_indices
)

for i, segment in enumerate(segments):
    if len(segment) == 0:
        continue

    portion = gauge.iloc[segment]

    ax.plot(
        portion["time_dc"],
        portion["plot_height"],
        color="steelblue",
        linewidth=1.5,
        label="Gauge height" if i == 0 else None
    )

ax.axvspan(
    event_start_dc,
    event_end_dc,
    color="orange",
    alpha=0.25,
    label="Reported flood interval"
)

ax.set_title(
    f"{STATION_NAME} — Gauge Height\n"
    f"Flood Event: {EVENT_ID}"
)

ax.set_xlabel(
    "Local time (America/New_York)"
)

ax.set_ylabel(
    f"Gauge height ({metadata['units']})"
)

ax.xaxis.set_major_formatter(
    mdates.DateFormatter(
        "%b %d\n%I:%M %p",
        tz=gauge["time_dc"].dt.tz
    )
)

ax.grid(alpha=0.3)
ax.legend()

plt.tight_layout()


# SECTION 6: Save the graph

ROOT = Path(__file__).resolve().parent.parent

FIGURE_DIR = ROOT / "outputs" / "figures"
FIGURE_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = (
    FIGURE_DIR /
    f"hdf5_gauge_{STATION_ID}_{EVENT_ID}.png"
)

plt.savefig(
    OUTPUT_FILE,
    dpi=300,
    bbox_inches="tight"
)

plt.show()


# SECTION 7: Print verification results

print("Graph saved to:", OUTPUT_FILE)
print("Typical sampling interval:", typical_interval)
print("Detected internal gaps:", len(gap_indices))

print(
    "Minimum gauge height:",
    gauge["gauge_height"].min()
)

print(
    "Maximum gauge height:",
    gauge["gauge_height"].max()
)

print("HDF5 gauge graph completed!")
