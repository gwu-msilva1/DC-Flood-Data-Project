
from pathlib import Path
import pandas as pd

# SECTION 1: Locate the files

ROOT = Path(__file__).resolve().parent.parent

EVENTS_FILE = (
    ROOT / "data" / "processed" /
    "flood_events_cleaned.csv"
)

STATIONS_FILE = (
    ROOT / "data" / "metadata" /
    "usgs_gauge_inventory.csv"
)

OUTPUT_FILE = (
    ROOT / "outputs" /
    "usgs_gauge_potential_coverage.csv"
)


# SECTION 2: Read the data

events = pd.read_csv(EVENTS_FILE)
stations = pd.read_csv(
    STATIONS_FILE,
    dtype={"station_id": str}
)

events["begin_date"] = pd.to_datetime(
    events["begin_date"]
)

events["end_date"] = pd.to_datetime(
    events["end_date"]
)

stations["start_date"] = pd.to_datetime(
    stations["start_date"]
)

stations["end_date"] = pd.to_datetime(
    stations["end_date"]
)


# SECTION 3: Compare events with stations

results = []

for _, station in stations.iterrows():

    for _, event in events.iterrows():

        station_start = station["start_date"]
        station_end = station["end_date"]

        # An empty end date means the station
        # has no published closure date in our inventory.
        if pd.isna(station_end):
            station_end = pd.Timestamp.max.normalize()

        # Does the event overlap the station's
        # published observation period?
        possible = (
            event["end_date"] >= station_start
            and event["begin_date"] <= station_end
        )

        results.append({
            "station_id": station["station_id"],
            "station_name": station["station_name"],
            "event_id": event["event_id"],
            "event_begin": event["begin_date"].date(),
            "event_end": event["end_date"].date(),
            "potential_coverage": possible
        })


# SECTION 4: Save the comparison table

coverage = pd.DataFrame(results)

coverage.to_csv(OUTPUT_FILE, index=False)


# SECTION 5: Print summary

summary = (
    coverage.groupby(
        ["station_id", "station_name"]
    )["potential_coverage"]
    .agg(
        possible_events="sum",
        total_events="count"
    )
    .reset_index()
)

print("\nPotential event coverage by station:")
print(summary.to_string(index=False))

print("\nTotal station-event combinations:",
      len(coverage))

print("\nCoverage file saved to:")
print(OUTPUT_FILE)

print("\nHistorical coverage comparison complete!")
