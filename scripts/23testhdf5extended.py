
from pathlib import Path
import json

import numpy as np
import pandas as pd

from hdf5functionsextended import (
    list_flood_events,
    list_data_sources,
    list_gauge_stations,
    get_database_metadata,
    get_event_precipitation,
    get_gauge_time_window,
    summarize_event_coverage
)


# SECTION 1: List events

print("\n=== TEST 1: FLOOD EVENTS ===")

events = list_flood_events()

print("Number of events:", len(events))
print("First five:", events[:5])

assert len(events) == 125


# SECTION 2: List sources

print("\n=== TEST 2: DATA SOURCES ===")

sources = list_data_sources()

for name, details in sources.items():
    print(name, details)

assert "PRISM" in sources
assert "USGS" in sources


# SECTION 3: List monitoring stations

print("\n=== TEST 3: GAUGE STATIONS ===")

stations = list_gauge_stations()

print("Number of stations:", len(stations))
print("Station IDs:", stations)

assert len(stations) == 4


# SECTION 4: Database metadata

print("\n=== TEST 4: DATABASE METADATA ===")

metadata = get_database_metadata()

print(
    "PRISM date range:",
    metadata["precipitation_date_range"]
)

print(
    "Stored precipitation dates:",
    metadata["precipitation_date_count"]
)

assert metadata["precipitation_date_count"] == 372


# SECTION 5: Event-related precipitation

print("\n=== TEST 5: EVENT PRECIPITATION ===")

rainfall, mask, prism_metadata = (
    get_event_precipitation("FLOOD_125")
)

print("Event:", prism_metadata["event_id"])
print("PRISM date:", prism_metadata["date"])
print("Grid shape:", rainfall.shape)
print("CRS:", prism_metadata["crs"])
print("Bounds:", prism_metadata["bounds"])
print("Valid cells:", int(mask.sum()))

assert prism_metadata["date"] == "20250719"
assert rainfall.shape == mask.shape
assert np.isfinite(rainfall[mask]).all()


# SECTION 6: Filter gauge observations

print("\n=== TEST 6: GAUGE TIME WINDOW ===")

window_start = "2025-07-19T12:00:00Z"
window_end = "2025-07-19T18:00:00Z"

gauge, gauge_metadata = get_gauge_time_window(
    "01648010",
    "FLOOD_125",
    start_utc=window_start,
    end_utc=window_end
)

print("Filtered observations:", len(gauge))

if not gauge.empty:
    print("First observation:", gauge["time_utc"].min())
    print("Last observation:", gauge["time_utc"].max())

assert len(gauge) > 0
assert (
    gauge["time_utc"].min()
    >= pd.Timestamp(window_start)
)
assert (
    gauge["time_utc"].max()
    <= pd.Timestamp(window_end)
)


# SECTION 7: Coverage summary

print("\n=== TEST 7: EVENT COVERAGE ===")

coverage = summarize_event_coverage("FLOOD_125")

print("\nPRISM coverage:")
print(coverage["prism"])

print("\nGauge coverage:")
print(
    coverage["gauges"].to_string(index=False)
)

assert coverage["prism"]["available_dates"] > 0

assert (
    coverage["gauges"]["available"].sum()
    >= 1
)


# SECTION 8: Save test results

ROOT = Path(__file__).resolve().parent.parent

OUT = ROOT / "outputs"
OUT.mkdir(parents=True, exist_ok=True)

coverage["gauges"].to_csv(
    OUT / "hdf5_event125_gauge_coverage.csv",
    index=False
)

with open(
    OUT / "hdf5_extended_prism_coverage.json",
    "w",
    encoding="utf-8"
) as file:
    json.dump(
        coverage["prism"],
        file,
        indent=4
    )

print("\nAll extended HDF5 tests passed!")
