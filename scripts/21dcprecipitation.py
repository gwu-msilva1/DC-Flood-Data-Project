
from pathlib import Path
from datetime import timezone, timedelta
from io import StringIO
import json

import h5py
import pandas as pd
import requests


# SECTION 1: Project locations

ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT / "data/processed/dc_precipitation"
REPORT_DIR = ROOT / "outputs/dc_precipitation"

DATA_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

HDF5_FILE = ROOT / "data/hdf5/dc_flood_data.h5"

STATION_ID = "USC00186350"
STATION_NAME = "National Arboretum, Washington DC"

START_DATE = "1996-01-01"
END_DATE = "2025-12-31"

API_URL = (
    "https://www.ncei.noaa.gov/"
    "access/services/data/v1"
)


# SECTION 2: Download the station observations

params = {
    "dataset": "daily-summaries",
    "stations": STATION_ID,
    "dataTypes": "PRCP",
    "startDate": START_DATE,
    "endDate": END_DATE,
    "units": "metric",
    "format": "csv",
    "includeAttributes": "true"
}

print("Investigating:", STATION_NAME)
print("Station ID:", STATION_ID)
print("Request period:", START_DATE, "to", END_DATE)

response = requests.get(
    API_URL, params=params, timeout=120
)

response.raise_for_status()

print("Final request URL:", response.url)

# A successful HTTP response is not necessarily valid CSV.
if response.text.lstrip().startswith(("{", "<")):
    raise ValueError(
        "NOAA returned JSON or HTML instead of CSV. "
        "Inspect the response and API parameters."
    )

df = pd.read_csv(
    StringIO(response.text),
    dtype={"STATION": str}
)

required = {"DATE", "PRCP"}

if not required.issubset(df.columns):
    raise ValueError(
        f"Expected columns {required}; "
        f"received {list(df.columns)}"
    )

raw_file = DATA_DIR / "noaa_arboretum_raw.csv"
raw_file.write_text(
    response.text, encoding="utf-8"
)

print("\nDownloaded rows:", len(df))
print("Available columns:", list(df.columns))


# SECTION 3: Clean the precipitation observations

df["DATE"] = pd.to_datetime(
    df["DATE"], errors="coerce"
)

df["PRCP"] = pd.to_numeric(
    df["PRCP"], errors="coerce"
)

df = df.rename(columns={
    "DATE": "date",
    "PRCP": "precipitation_mm"
})

df = df.sort_values("date").reset_index(drop=True)

clean_file = DATA_DIR / "noaa_arboretum_daily.csv"

df.to_csv(clean_file, index=False)

print("Valid observation dates:",
      df["date"].notna().sum())

print("Usable rainfall values:",
      df["precipitation_mm"].notna().sum())

print("First observation:", df["date"].min())
print("Last observation:", df["date"].max())


# SECTION 4: Retrieve flood-event dates from HDF5

# The instructor's original dates use fixed EST (UTC-5).
FIXED_EST = timezone(timedelta(hours=-5))

event_rows = []

with h5py.File(HDF5_FILE, "r") as h5:

    event_ids = h5["events/event_ids"].asstr()[:]

    for event_id in event_ids:

        record_text = (
            h5[f"events/{event_id}/record_json"]
            .asstr()[()]
        )

        record = json.loads(record_text)

        start_utc = pd.to_datetime(
            record["begin_utc"], utc=True
        )

        local_date = (
            start_utc.tz_convert(FIXED_EST).date()
        )

        event_rows.append({
            "event_id": event_id,
            "event_start_date_fixed_est": local_date
        })

events = pd.DataFrame(event_rows)


# SECTION 5: Compare station data with flood dates

# Do not confuse a missing observation with zero rain.
valid_observations = (
    df.dropna(subset=["date", "precipitation_mm"])
    .copy()
)

valid_observations["comparison_date"] = (
    valid_observations["date"].dt.date
)

event_coverage = events.merge(
    valid_observations[
        ["comparison_date", "precipitation_mm"]
    ],
    left_on="event_start_date_fixed_est",
    right_on="comparison_date",
    how="left"
)

event_coverage["precipitation_available"] = (
    event_coverage["precipitation_mm"].notna()
)

coverage_file = (
    REPORT_DIR / "arboretum_event_date_coverage.csv"
)

event_coverage.to_csv(
    coverage_file, index=False
)


# SECTION 6: Summarize the investigation

total_events = len(events)

covered_events = int(
    event_coverage["precipitation_available"].sum()
)

summary = {
    "station_id": STATION_ID,
    "station_name": STATION_NAME,
    "latitude": 38.91329,
    "longitude": -76.97009,
    "source": "NOAA NCEI Daily Summaries",
    "variable": "PRCP",
    "requested_units": "metric (mm)",
    "requested_start": START_DATE,
    "requested_end": END_DATE,
    "downloaded_rows": int(len(df)),
    "valid_precipitation_rows": int(
        df["precipitation_mm"].notna().sum()
    ),
    "event_count": total_events,
    "events_with_same_date_observation": covered_events,
    "events_without_same_date_observation": (
        total_events - covered_events
    ),
    "request_url": response.url,
    "note": (
        "Same-date coverage is preliminary. "
        "Daily observation periods and time-zone "
        "alignment require separate verification."
    )
}

summary_file = REPORT_DIR / "arboretum_summary.json"

with open(summary_file, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=4)


# SECTION 7: Final terminal output

print("\n=== IN-DC PRECIPITATION INVESTIGATION ===")

print("NOAA rows:", len(df))
print("Flood events:", total_events)
print("Events with same-date rainfall:", covered_events)
print(
    "Events without same-date rainfall:",
    total_events - covered_events
)

print("\nDaily observations saved to:")
print(clean_file)

print("\nCoverage report saved to:")
print(coverage_file)

print("\nSummary saved to:")
print(summary_file)

print("\nInvestigation complete!")
