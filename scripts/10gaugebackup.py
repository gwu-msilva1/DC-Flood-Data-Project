
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse
import json
import time

import pandas as pd
import requests


# SECTION 1: Project folders and settings

ROOT = Path(__file__).resolve().parent.parent

EVENTS_FILE = (
    ROOT / "data" / "processed" /
    "flood_events_cleaned.csv"
)

STATIONS_FILE = (
    ROOT / "data" / "metadata" /
    "usgs_gauge_inventory.csv"
)

GAUGE_DIR = ROOT / "data" / "processed" / "gauges"
OUTPUT_DIR = ROOT / "outputs"

GAUGE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

REPORT_FILE = OUTPUT_DIR / "usgs_gauge_availability.csv"

API_URL = (
    "https://api.waterdata.usgs.gov/ogcapi/v1/"
    "collections/continuous/items"
)

PARAMETER_CODE = "00065"

# Start with a small test
STATION_LIMIT = 4
EVENT_LIMIT = 3

# Hours before and after the reported event
BUFFER_HOURS = 24

MAX_ATTEMPTS = 3


# SECTION 2: Load events and stations

events = pd.read_csv(
    EVENTS_FILE, dtype={"event_id": str}
)

stations = pd.read_csv(
    STATIONS_FILE, dtype={"station_id": str}
)

events["begin_utc"] = pd.to_datetime(
    events["begin_utc"], utc=True, errors="coerce"
)

events["end_utc"] = pd.to_datetime(
    events["end_utc"], utc=True, errors="coerce"
)

if events["event_id"].duplicated().any():
    raise ValueError("Duplicate flood event IDs.")

if events[["begin_utc", "end_utc"]].isna().any().any():
    raise ValueError("Some event timestamps are missing.")

if (events["end_utc"] < events["begin_utc"]).any():
    raise ValueError("An event ends before it begins.")

stations["start_date"] = pd.to_datetime(
    stations["start_date"], errors="coerce", utc=True
)

stations["end_date"] = pd.to_datetime(
    stations["end_date"], errors="coerce", utc=True
)

print("Flood events:", len(events))
print("Stations:", len(stations))


# SECTION 3: Helper functions

def utc_string(value):
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def paths_for(station_id, event_id):
    base = f"gauge_USGS-{station_id}_{event_id}"

    return (
        GAUGE_DIR / f"{base}.csv",
        GAUGE_DIR / f"{base}_metadata.json"
    )


def make_window(event):
    start = event["begin_utc"] - pd.Timedelta(
        hours=BUFFER_HOURS
    )
    end = event["end_utc"] + pd.Timedelta(
        hours=BUFFER_HOURS
    )
    return start, end


# SECTION 4: Download pages from USGS

session = requests.Session()

session.headers.update({
    "User-Agent": "STAT6289-DC-Flood-Project/1.0"
})


def get_with_retry(url, params=None):

    for attempt in range(1, MAX_ATTEMPTS + 1):

        try:
            response = session.get(
                url, params=params, timeout=90
            )
            response.raise_for_status()
            return response.json()

        except requests.HTTPError as exc:
            status = exc.response.status_code

            if (
                status not in (429, 500, 502, 503, 504)
                or attempt == MAX_ATTEMPTS
            ):
                raise

        except (requests.Timeout, requests.ConnectionError):
            if attempt == MAX_ATTEMPTS:
                raise

        print(f"Temporary error; retry {attempt}")
        time.sleep(2 ** attempt)


def download_observations(station_id, start, end):

    params = {
        "f": "json",
        "monitoring_location_id": f"USGS-{station_id}",
        "parameter_code": PARAMETER_CODE,
        "datetime": (
            f"{utc_string(start)}/{utc_string(end)}"
        ),
        "limit": 1000
    }

    features = []
    next_url = API_URL
    next_params = params
    visited = set()

    while next_url:

        # Prevent pagination loops
        request_key = (next_url, str(next_params))

        if request_key in visited:
            raise RuntimeError("Repeated pagination request.")

        visited.add(request_key)

        result = get_with_retry(
            next_url, params=next_params
        )

        features.extend(result.get("features", []))

        next_link = next(
            (
                link.get("href")
                for link in result.get("links", [])
                if link.get("rel") == "next"
            ),
            None
        )

        if next_link:
            parsed = urlparse(next_link)

            if (
                parsed.scheme != "https"
                or parsed.hostname != "api.waterdata.usgs.gov"
            ):
                raise ValueError(
                    "Unexpected pagination destination."
                )

        next_url = next_link
        next_params = None

    return features, params


# SECTION 5: Convert observations to a DataFrame

def make_dataframe(features, station_id, start, end):

    records = []

    for feature in features:

        p = feature.get("properties", {})

        if (
            p.get("monitoring_location_id")
            != f"USGS-{station_id}"
        ):
            continue

        if str(p.get("parameter_code")) != PARAMETER_CODE:
            continue

        records.append({
            "station_id": f"USGS-{station_id}",
            "time_utc": p.get("time"),
            "gauge_height": p.get("value"),
            "unit": p.get("unit_of_measure"),
            "approval_status": p.get("approval_status"),
            "qualifier": json.dumps(
                p.get("qualifier")
            ),
            "time_series_id": p.get(
                "time_series_id",
                p.get("timeseries_id")
            )
        })

    columns = [
        "station_id", "time_utc", "gauge_height",
        "unit", "approval_status", "qualifier",
        "time_series_id"
    ]

    df = pd.DataFrame(records, columns=columns)

    df["time_utc"] = pd.to_datetime(
        df["time_utc"], utc=True, errors="coerce"
    )

    df["gauge_height"] = pd.to_numeric(
        df["gauge_height"], errors="coerce"
    )

    df = df.dropna(subset=["time_utc"])

    df = df.loc[
        (df["time_utc"] >= start) &
        (df["time_utc"] <= end)
    ].copy()

    df = df.drop_duplicates()

    df = df.sort_values(
        ["time_utc", "time_series_id"],
        na_position="last"
    ).reset_index(drop=True)

    df["time_dc"] = df["time_utc"].dt.tz_convert(
        "America/New_York"
    )

    return df


# SECTION 6: Check previously downloaded files

def check_existing(station_id, event_id):

    csv_path, metadata_path = paths_for(
        station_id, event_id
    )

    if not csv_path.exists() or not metadata_path.exists():
        return None

    try:
        with open(metadata_path, encoding="utf-8") as f:
            metadata = json.load(f)

        if (
            metadata.get("station_id")
            != f"USGS-{station_id}"
            or metadata.get("event_id") != event_id
        ):
            return None

        df = pd.read_csv(csv_path)

        if len(df) != metadata.get("records"):
            return None

        return metadata

    except (OSError, ValueError, KeyError, TypeError):
        return None


# SECTION 7: Build full station-event inventory

combinations = []

for _, station in stations.iterrows():

    for _, event in events.iterrows():

        start, end = make_window(event)

        # Convert broad published coverage dates
        # into a preliminary eligibility check.
        station_start = station["start_date"]
        station_end = station["end_date"]

        potentially_available = True

        if pd.notna(station_start):
            if end < station_start:
                potentially_available = False

        if pd.notna(station_end):
            # Include the station's final calendar day.
            final_day = (
                station_end + pd.Timedelta(days=1)
            )

            if start >= final_day:
                potentially_available = False

        combinations.append({
            "station_id": station["station_id"],
            "station_name": station["station_name"],
            "event_id": event["event_id"],
            "window_start": start,
            "window_end": end,
            "potentially_available": potentially_available
        })

inventory = pd.DataFrame(combinations)

print("Station-event combinations:", len(inventory))


# SECTION 8: Load previous batch results

if REPORT_FILE.exists():
    previous = pd.read_csv(
        REPORT_FILE,
        dtype={"station_id": str, "event_id": str}
    )
    previous = {
        (r["station_id"], r["event_id"]): r
        for _, r in previous.iterrows()
    }
else:
    previous = {}

results = {}

for _, item in inventory.iterrows():

    key = (item["station_id"], item["event_id"])
    old = previous.get(key, {})

    if not item["potentially_available"]:
        status = "outside_published_period"
    else:
        status = old.get("status", "not_attempted")

        if status not in (
            "available", "no_observations",
            "partial", "failed"
        ):
            status = "not_attempted"

    results[key] = {
        "station_id": item["station_id"],
        "station_name": item["station_name"],
        "event_id": item["event_id"],
        "window_start_utc": utc_string(
            item["window_start"]
        ),
        "window_end_utc": utc_string(
            item["window_end"]
        ),
        "status": status,
        "records": old.get("records", 0),
        "valid_records": old.get("valid_records", 0),
        "error": old.get("error", "")
    }


def save_report():
    pd.DataFrame(
        list(results.values())
    ).to_csv(REPORT_FILE, index=False)


# SECTION 9: Select test combinations

eligible = inventory.loc[
    inventory["potentially_available"]
].copy()

# Follow the station order in our inventory.
selected_stations = (
    stations["station_id"].tolist()
    if STATION_LIMIT is None
    else stations["station_id"].tolist()[:STATION_LIMIT]
)

selected = []

for station_id in selected_stations:

    subset = eligible.loc[
        eligible["station_id"] == station_id
    ]

    # Start with the most recent events.
    subset = subset.sort_values(
        "window_start", ascending=False
    )

    if EVENT_LIMIT is not None:
        subset = subset.head(EVENT_LIMIT)

    selected.extend(
        subset.to_dict("records")
    )

print("Selected combinations:", len(selected))


# SECTION 10: Download selected combinations

for i, item in enumerate(selected, start=1):

    station_id = item["station_id"]
    event_id = item["event_id"]
    key = (station_id, event_id)

    print(
        f"\nProcessing {i}/{len(selected)}: "
        f"{station_id} / {event_id}"
    )

    try:
        existing = check_existing(
            station_id, event_id
        )

        if existing is not None and (
            existing.get("status") == "available"
        ):
            metadata = existing
            action = "reused"

        else:
            start = item["window_start"]
            end = item["window_end"]

            features, request_params = (
                download_observations(
                    station_id, start, end
                )
            )

            df = make_dataframe(
                features, station_id, start, end
            )

            valid = int(
                df["gauge_height"].notna().sum()
            )

            status = (
                "available" if valid > 0
                else "no_observations"
            )

            csv_path, metadata_path = paths_for(
                station_id, event_id
            )

            df.to_csv(csv_path, index=False)

            metadata = {
                "station_id": f"USGS-{station_id}",
                "station_name": item["station_name"],
                "event_id": event_id,
                "parameter_code": PARAMETER_CODE,
                "variable": "gauge height",
                "status": status,
                "window_start_utc": utc_string(start),
                "window_end_utc": utc_string(end),
                "records": len(df),
                "valid_records": valid,
                "units": sorted(
                    df["unit"].dropna().unique().tolist()
                ),
                "approval_statuses": (
                    df["approval_status"]
                    .value_counts(dropna=False)
                    .to_dict()
                ),
                "time_series_ids": (
                    df["time_series_id"]
                    .dropna().astype(str).unique().tolist()
                ),
                "api_url": API_URL,
                "api_parameters": request_params,
                "retrieved_at_utc": datetime.now(
                    timezone.utc
                ).isoformat(),
                "timestamp_note": (
                    "USGS times in UTC; event index "
                    "uses instructor-specified fixed EST."
                )
            }

            with open(
                metadata_path, "w", encoding="utf-8"
            ) as f:
                json.dump(metadata, f, indent=4)

            action = "downloaded"

        results[key].update({
            "status": metadata["status"],
            "records": metadata["records"],
            "valid_records": metadata["valid_records"],
            "error": ""
        })

        print(
            "Result:", action,
            "| Status:", metadata["status"],
            "| Valid values:", metadata["valid_records"]
        )

    except Exception as exc:

        results[key].update({
            "status": "failed",
            "error": str(exc)
        })

        print("Failed:", exc)

    save_report()

    # Brief spacing between requests
    time.sleep(1)


# SECTION 11: Final summary

save_report()

report = pd.read_csv(REPORT_FILE)

print("\nBatch processing complete!")

print("\nStation-event availability:")
print(report["status"].value_counts())

print("\nReport saved to:")
print(REPORT_FILE)
