
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
VALIDATION_ONLY = True


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


# SECTION 6: Validate previously downloaded files

def check_existing(station_id, event_id, start, end):

    csv_path, metadata_path = paths_for(
        station_id, event_id
    )

    # Both files must exist.
    if not csv_path.exists() or not metadata_path.exists():
        return None

    try:
        # Read the metadata.
        with open(metadata_path, encoding="utf-8") as f:
            metadata = json.load(f)

        expected_station = f"USGS-{station_id}"

        # Check station and event identities.
        if metadata.get("station_id") != expected_station:
            return None

        if metadata.get("event_id") != event_id:
            return None

        if metadata.get("parameter_code") != PARAMETER_CODE:
            return None

        if metadata.get("status") != "available":
            return None

        # Check the requested observation window.
        saved_start = pd.to_datetime(
            metadata.get("window_start_utc"),
            utc=True
        )

        saved_end = pd.to_datetime(
            metadata.get("window_end_utc"),
            utc=True
        )

        if saved_start != start or saved_end != end:
            return None

        # Read the saved observations.
        df = pd.read_csv(
            csv_path,
            dtype={"station_id": str}
        )

        required_columns = [
            "station_id",
            "time_utc",
            "gauge_height",
            "unit",
            "approval_status"
        ]

        if not all(
            column in df.columns
            for column in required_columns
        ):
            return None

        if df.empty:
            return None

        # Check station IDs in every row.
        if not (
            df["station_id"] == expected_station
        ).all():
            return None

        # Convert and validate timestamps.
        times = pd.to_datetime(
            df["time_utc"],
            utc=True,
            errors="coerce"
        )

        if times.isna().any():
            return None

        if (
            (times < start) | (times > end)
        ).any():
            return None

        # Check for repeated timestamps.
        # Multiple series could produce legitimate
        # overlapping times, so flag these for
        # review instead of deleting observations.
        if times.duplicated().any():
            return None

        heights = pd.to_numeric(
            df["gauge_height"],
            errors="coerce"
        )

        valid = int(heights.notna().sum())

        if valid == 0:
            return None

        # Basic measurement unit check.
        units = set(
            df["unit"].dropna().astype(str)
        )

        if units != {"ft"}:
            return None

        # Compare actual counts with metadata.
        if len(df) != metadata.get("records"):
            return None

        if valid != metadata.get("valid_records"):
            return None

        # Determine typical observation interval.
        sorted_times = times.sort_values()
        differences = (
            sorted_times.diff()
            .dropna()
            .dt.total_seconds() / 60
        )

        if differences.empty:
            return None

        typical_interval = float(
            differences.mode().iloc[0]
        )

        if typical_interval <= 0:
            return None

        # Flag unusually large internal gaps.
        largest_interval = float(
            differences.max()
        )

        if largest_interval > 1.5 * typical_interval:
            return None

        # Check the beginning and end of the window.
        first_time = sorted_times.iloc[0]
        last_time = sorted_times.iloc[-1]

        start_gap = (
            first_time - start
        ).total_seconds() / 60

        end_gap = (
            end - last_time
        ).total_seconds() / 60

        # A normal boundary gap should be smaller
        # than approximately one sampling interval.
        tolerance = typical_interval + 0.01

        if start_gap > tolerance:
            return None

        if end_gap > tolerance:
            return None

        return metadata

    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        pd.errors.ParserError
    ):
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
        # Get the requested observation window.
        start = item["window_start"]
        end = item["window_end"]

        # Check previously saved files using
        # the improved validator from Section 6.
        existing = check_existing(
            station_id,
            event_id,
            start,
            end
        )

        # Find the expected output files.
        csv_path, metadata_path = paths_for(
            station_id, event_id
        )

        # Notify us if saved files fail validation.
        if existing is None and (
            csv_path.exists() or metadata_path.exists()
        ):
            print(
                "Existing files did not pass validation."
            )

        # CASE 1: Existing files passed validation.
        if existing is not None:

            metadata = existing
            action = "reused"

        # CASE 2: No validated files are available.
        else:

            # During validation-only testing,
            # do not download or overwrite any files.
            if VALIDATION_ONLY:
                print(
                    "Validation-only mode: "
                    "no download attempted."
                )

                # Preserve existing reports and files.
                # Mark only the action for this test.
                if csv_path.exists() or metadata_path.exists():
                    print(
                        "Saved files need further review."
                    )
                else:
                    print(
                        "No existing files found."
                    )

                continue

            # Download observations from USGS.
            features, request_params = (
                download_observations(
                    station_id,
                    start,
                    end
                )
            )

            # Convert observations into a DataFrame.
            df = make_dataframe(
                features,
                station_id,
                start,
                end
            )

            # Count valid gauge-height measurements.
            valid = int(
                df["gauge_height"].notna().sum()
            )

            status = (
                "available" if valid > 0
                else "no_observations"
            )

            # Protect files that already exist but
            # did not pass validation.
            if csv_path.exists() or metadata_path.exists():
                raise RuntimeError(
                    "Existing files failed validation. "
                    "Refusing to overwrite them."
                )

            # Save the observations.
            df.to_csv(csv_path, index=False)

            # Create metadata for this station-event pair.
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
                    .dropna()
                    .astype(str)
                    .unique()
                    .tolist()
                ),
                "api_url": API_URL,
                "api_parameters": request_params,
                "retrieved_at_utc": datetime.now(
                    timezone.utc
                ).isoformat(),
                "timestamp_note": (
                    "USGS observations are stored in UTC. "
                    "Flood-event timestamps use "
                    "instructor-specified fixed EST "
                    "(UTC-5)."
                )
            }

            # Save metadata to JSON.
            with open(
                metadata_path,
                "w",
                encoding="utf-8"
            ) as f:
                json.dump(metadata, f, indent=4)

            action = "downloaded"

        # Update the availability report after
        # either a successful download or reuse.
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

        # Record errors without stopping the batch.
        results[key].update({
            "status": "failed",
            "error": str(exc)
        })

        print("Failed:", exc)

    # Save progress after every processed combination.
    save_report()

    # Brief spacing between requests.
    if not VALIDATION_ONLY:
        time.sleep(1)


# SECTION 11: Final summary

save_report()

report = pd.read_csv(REPORT_FILE)

print("\nBatch processing complete!")

print("\nStation-event availability:")
print(report["status"].value_counts())

print("\nReport saved to:")
print(REPORT_FILE)
