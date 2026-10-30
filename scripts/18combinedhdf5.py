
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

from hdf5_functions import (
    get_precipitation,
    get_gauge_data,
    get_flood_event
)


# SECTION 1: Choose the flood event

EVENT_ID = "FLOOD_125"
PRISM_DATE = "2025-07-19"

STATION_ID = "01648010"
STATION_NAME = "Rock Creek at Joyce Road"


# SECTION 2: Locate the output folder

ROOT = Path(__file__).resolve().parent.parent

FIGURE_DIR = ROOT / "outputs" / "figures"
FIGURE_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = (
    FIGURE_DIR /
    f"hdf5_combined_{EVENT_ID}.png"
)


# SECTION 3: Retrieve all data from HDF5

event = get_flood_event(EVENT_ID)

rainfall, mask, prism_metadata = get_precipitation(
    PRISM_DATE
)

gauge, gauge_metadata = get_gauge_data(
    STATION_ID,
    EVENT_ID
)

print("Selected event:", EVENT_ID)
print("PRISM date:", PRISM_DATE)
print("Gauge station:", STATION_NAME)
print("Gauge observations:", len(gauge))


# SECTION 4: Prepare the precipitation data

rainfall = np.where(
    mask,
    rainfall,
    np.nan
)

left, bottom, right, top = prism_metadata["bounds"]

print("PRISM grid dimensions:", rainfall.shape)

if np.isfinite(rainfall).any():
    print(
        "Maximum daily precipitation (mm):",
        np.nanmax(rainfall)
    )


# SECTION 5: Prepare the gauge observations

gauge = gauge.sort_values(
    "time_utc"
).reset_index(drop=True)

# Work in UTC for accurate temporal comparison.
gauge["time_utc"] = pd.to_datetime(
    gauge["time_utc"], utc=True
)

event_start = pd.to_datetime(
    event["begin_utc"], utc=True
)

event_end = pd.to_datetime(
    event["end_utc"], utc=True
)

# Convert UTC values to local clock time for plotting.
# The instructor's event times were originally fixed
# EST; UTC conversion has already been completed.
local_timezone = "America/New_York"

event_start_local = event_start.tz_convert(
    local_timezone
)

event_end_local = event_end.tz_convert(
    local_timezone
)

gauge["time_local"] = (
    gauge["time_utc"].dt.tz_convert(local_timezone)
)


# SECTION 6: Identify gaps in gauge observations

time_differences = (
    gauge["time_utc"]
    .diff()
    .dt.total_seconds() / 60
)

intervals = time_differences.dropna()

if len(intervals):
    typical_interval = float(
        intervals.mode().iloc[0]
    )
else:
    typical_interval = np.nan

if pd.notna(typical_interval):
    gap_indices = np.where(
        time_differences.to_numpy()
        > 1.5 * typical_interval
    )[0]
else:
    gap_indices = []

print(
    "Typical gauge interval (minutes):",
    typical_interval
)

print("Detected internal gaps:", len(gap_indices))


# SECTION 7: Create the combined figure

fig, axes = plt.subplots(
    1,
    2,
    figsize=(16, 6.5),
    gridspec_kw={"width_ratios": [1, 1.35]}
)

ax_map = axes[0]
ax_gauge = axes[1]


# SECTION 8: Panel A - PRISM precipitation

image = ax_map.imshow(
    rainfall,
    extent=[left, right, bottom, top],
    origin="upper",
    cmap="Blues",
    vmin=0,
    interpolation="nearest",
    aspect="equal"
)

colorbar = fig.colorbar(
    image,
    ax=ax_map,
    fraction=0.046,
    pad=0.04
)

colorbar.set_label("Daily precipitation (mm)")

ax_map.set_title(
    f"A. PRISM Daily Precipitation\n{PRISM_DATE}"
)

ax_map.set_xlabel("Longitude (degrees)")
ax_map.set_ylabel("Latitude (degrees)")
ax_map.grid(alpha=0.12)


# SECTION 9: Panel B - USGS gauge height

# Plot separate segments to avoid connecting
# across periods with missing observations.
segments = np.split(
    np.arange(len(gauge)),
    gap_indices
)

for i, indices in enumerate(segments):

    if len(indices) == 0:
        continue

    subset = gauge.iloc[indices]

    ax_gauge.plot(
        subset["time_local"],
        subset["gauge_height"],
        linewidth=1.5,
        color="steelblue",
        label="Gauge height" if i == 0 else None
    )

# Highlight the reported flood interval.
ax_gauge.axvspan(
    event_start_local,
    event_end_local,
    color="orange",
    alpha=0.28,
    label="Reported flood interval"
)

ax_gauge.set_title(
    f"B. {STATION_NAME}\n"
    f"Gauge Height — {EVENT_ID}"
)

ax_gauge.set_xlabel(
    "Local clock time (America/New_York)"
)

ax_gauge.set_ylabel(
    f"Gauge height ({gauge_metadata['units']})"
)

ax_gauge.xaxis.set_major_formatter(
    mdates.DateFormatter(
        "%b %d\n%I:%M %p",
        tz=gauge["time_local"].dt.tz
    )
)

ax_gauge.grid(alpha=0.25)
ax_gauge.legend(loc="best")


# SECTION 10: Add title and source information

fig.suptitle(
    "Washington, DC Flood Event — "
    f"{EVENT_ID}",
    fontsize=16,
    fontweight="bold"
)

fig.text(
    0.5,
    0.015,
    "Sources: PRISM Climate Group (daily precipitation); "
    "USGS (gauge-height observations). "
    "Both retrieved from the project HDF5 database.",
    ha="center",
    fontsize=9
)

plt.tight_layout(
    rect=[0, 0.055, 1, 0.94]
)


# SECTION 11: Save and display the figure

plt.savefig(
    OUTPUT_FILE,
    dpi=300,
    bbox_inches="tight"
)

print("\nCombined figure saved to:")
print(OUTPUT_FILE)

plt.show()

print("\nCombined HDF5 visualization complete!")
