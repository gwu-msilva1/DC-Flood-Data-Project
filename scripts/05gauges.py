
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse
import json

import pandas as pd
import requests


# SECTION 1: Locate the project folders

ROOT = Path(__file__).resolve().parent.parent

EVENTS_FILE = (
    ROOT / "data" / "processed" /
    "flood_events_cleaned.csv"
)

GAUGE_DIR = ROOT / "data" / "processed" / "gauges"
GAUGE_DIR.mkdir(parents=True, exist_ok=True)


# SECTION 2: Select the station and flood event

STATION_ID = "USGS-01648010"
STATION_NAME = "Rock Creek at Joyce Road, Washington DC"
PARAMETER_CODE = "00065"
EVENT_ID = "FLOOD_125"

events = pd.read_csv(EVENTS_FILE)

event = events.loc[events["event_id"] == EVENT_ID]

if len(event) != 1:
    raise ValueError("Expected exactly one matching event.")

event = event.iloc[0]

# Use the UTC timestamps created during Step 2.
# These must reflect the professor's fixed EST convention.

start_utc = pd.to_datetime(
    event["begin_utc"], utc=True
)

end_utc = pd.to_datetime(
    event["end_utc"], utc=True
)

if pd.isna(start_utc) or pd.isna(end_utc):
    raise ValueError("Event has invalid UTC timestamps.")

# Expand the observation window by one day.
window_start = start_utc - pd.Timedelta(days=1)
window_end = end_utc + pd.Timedelta(days=1)

print("Selected event:", EVENT_ID)
print("Gauge:", STATION_NAME)
print("Event starts (UTC):", start_utc)
print("Event ends (UTC):", end_utc)
print("Requested window:", window_start, "to", window_end)


# SECTION 3: Prepare the USGS request

API_URL = (
    "https://api.waterdata.usgs.gov/ogcapi/v1/"
    "collections/continuous/items"
)

def utc_string(timestamp):
    return timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")

params = {
    "f": "json",
    "monitoring_location_id": STATION_ID,
    "parameter_code": PARAMETER_CODE,
    "datetime": (
        utc_string(window_start) + "/" +
        utc_string(window_end)
    ),
    "limit": 1000
}

print("\nContacting the USGS data service...")

session = requests.Session()
session.headers.update({
    "User-Agent": "STAT6289-DC-Flood-Research/1.0"
})

# SECTION 4: Retrieve all available pages

features = []
next_url = API_URL
next_params = params
visited_urls = set()

while next_url:

    response = session.get(
        next_url,
        params=next_params,
        timeout=60
    )

    response.raise_for_status()

    if response.url in visited_urls:
        raise RuntimeError("Repeated API pagination URL.")

    visited_urls.add(response.url)

    result = response.json()

    page_features = result.get("features", [])
    features.extend(page_features)

    print(
        "Received", len(page_features),
        "observations on this page."
    )

    # The service may paginate larger results.
    next_link = next(
        (
            link.get("href")
            for link in result.get("links", [])
            if link.get("rel") == "next"
        ),
        None
    )

    if next_link:
        # Follow only HTTPS links to the same API host.
        parsed = urlparse(next_link)

        if (
            parsed.scheme != "https"
            or parsed.netloc != "api.waterdata.usgs.gov"
        ):
            raise ValueError("Unexpected pagination URL.")

    next_url = next_link
    next_params = None

print("\nTotal returned observations:", len(features))


# SECTION 5: Convert the observations into a table

records = []

for feature in features:

    properties = feature.get("properties", {})

    if (
        properties.get("monitoring_location_id") != STATION_ID
        or properties.get("parameter_code") != PARAMETER_CODE
    ):
        continue

    records.append({
        "station_id": STATION_ID,
        "time_utc": properties.get("time"),
        "gauge_height": properties.get("value"),
        "unit": properties.get("unit_of_measure"),
        "approval_status": properties.get("approval_status"),
        "qualifier": str(properties.get("qualifier")),
        "timeseries_id": properties.get("timeseries_id")
    })

columns = [
    "station_id", "time_utc", "gauge_height",
    "unit", "approval_status", "qualifier",
    "timeseries_id"
]

df = pd.DataFrame(records, columns=columns)

df["time_utc"] = pd.to_datetime(
    df["time_utc"], utc=True
)

df["gauge_height"] = pd.to_numeric(
    df["gauge_height"], errors="coerce"
)

df = df.dropna(subset=["time_utc"])
df = df.sort_values("time_utc").reset_index(drop=True)

# Keep only observations in our requested window.
df = df.loc[
    (df["time_utc"] >= window_start) &
    (df["time_utc"] <= window_end)
].copy()

# Preserve source timestamps in UTC and add
# a local display-time column for interpretation.
df["time_dc"] = (
    df["time_utc"]
    .dt.tz_convert("America/New_York")
)

# SECTION 6: Save the data

output_file = GAUGE_DIR / (
    f"gauge_{STATION_ID}_{EVENT_ID}.csv"
)

df.to_csv(output_file, index=False)

metadata = {
    "source": "United States Geological Survey",
    "station_id": STATION_ID,
    "station_name": STATION_NAME,
    "parameter_code": PARAMETER_CODE,
    "variable": "gauge height",
    "event_id": EVENT_ID,
    "start_utc": utc_string(window_start),
    "end_utc": utc_string(window_end),
    "source_url": API_URL,
    "source_parameters": params,
    "retrieved_at_utc": datetime.now(
        timezone.utc
    ).isoformat(),
    "returned_records": len(df),
    "valid_height_records": int(
        df["gauge_height"].notna().sum()
    ),
    "units_reported": (
        df["unit"].dropna().unique().tolist()
    ),
    "note": (
        "Source timestamps are UTC. Flood-event "
        "timestamps were originally supplied in "
        "fixed EST (UTC-5). Display time uses "
        "America/New_York for local civil time."
    )
}

metadata_file = GAUGE_DIR / (
    f"gauge_{STATION_ID}_{EVENT_ID}_metadata.json"
)

with open(metadata_file, "w", encoding="utf-8") as f:
    json.dump(metadata, f, indent=4)


# SECTION 7: Print a summary

print("\nFirst five observations:")
print(df.head().to_string(index=False))

print("\nNumber of rows:", len(df))
print(
    "Valid gauge-height measurements:",
    df["gauge_height"].notna().sum()
)

if not df.empty:
    print("\nReported units:")
    print(df["unit"].value_counts(dropna=False))

print("\nCSV saved to:", output_file)
print("Metadata saved to:", metadata_file)
print("\nGauge download test complete!")
