
from pathlib import Path
import pandas as pd
import requests
import time

# SECTION 1: Locate project files

ROOT = Path(__file__).resolve().parent.parent

INVENTORY_FILE = (
    ROOT / "data" / "metadata" /
    "usgs_gauge_inventory.csv"
)

EVENTS_FILE = (
    ROOT / "data" / "processed" /
    "flood_events_cleaned.csv"
)

OUTPUT_FILE = (
    ROOT / "outputs" /
    "usgs_gauge_verification.csv"
)


# SECTION 2: Read station inventory

stations = pd.read_csv(
    INVENTORY_FILE,
    dtype={"station_id": str}
)

events = pd.read_csv(EVENTS_FILE)

event = events.loc[
    events["event_id"] == "FLOOD_125"
].iloc[0]

# Corrected event UTC timestamp from Step 2
start_utc = pd.to_datetime(
    event["begin_utc"],
    utc=True
)

# We will request a two-hour test window.
end_utc = start_utc + pd.Timedelta(hours=2)

def format_utc(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")

print("Test event: FLOOD_125")
print("Start:", start_utc)
print("End:", end_utc)


# SECTION 3: Set up the USGS API

API_URL = (
    "https://api.waterdata.usgs.gov/ogcapi/v1/"
    "collections/continuous/items"
)

PARAMETER_CODE = "00065"

session = requests.Session()

session.headers.update({
    "User-Agent": "STAT6289-DC-Flood-Project/1.0"
})


# SECTION 4: Test each station

results = []

for _, station in stations.iterrows():

    station_id = station["station_id"]
    full_id = "USGS-" + station_id

    print("\n-----------------------------")
    print("Checking:", station["station_name"])
    print("Station ID:", full_id)

    params = {
        "f": "json",
        "monitoring_location_id": full_id,
        "parameter_code": PARAMETER_CODE,
        "datetime": (
            format_utc(start_utc) + "/" +
            format_utc(end_utc)
        ),
        "limit": 1000
    }

    status = "not_verified"
    records_found = 0
    valid_values = 0
    units = ""
    error_message = ""

    try:
        response = session.get(
            API_URL,
            params=params,
            timeout=60
        )

        response.raise_for_status()

        data = response.json()

        features = data.get("features", [])

        matching = []

        for feature in features:

            p = feature.get("properties", {})

            if (
                p.get("monitoring_location_id") == full_id
                and p.get("parameter_code")
                    == PARAMETER_CODE
            ):
                matching.append(p)

        records_found = len(matching)

        values = pd.to_numeric(
            [
                p.get("value")
                for p in matching
            ],
            errors="coerce"
        )

        valid_values = int(
            pd.Series(values).notna().sum()
        )

        units = ";".join(
            sorted({
                str(p["unit_of_measure"])
                for p in matching
                if p.get("unit_of_measure")
            })
        )

        if valid_values > 0:
            status = "observations_confirmed"

        else:
            status = "no_usable_observations"

        print("Records:", records_found)
        print("Valid heights:", valid_values)
        print("Units:", units)
        print("Status:", status)

    except (requests.RequestException, ValueError) as exc:

        status = "request_failed"
        error_message = str(exc)

        print("Request failed:", error_message)

    results.append({
        "station_id": station_id,
        "station_name": station["station_name"],
        "parameter_code": PARAMETER_CODE,
        "test_event": "FLOOD_125",
        "window_start_utc": format_utc(start_utc),
        "window_end_utc": format_utc(end_utc),
        "status": status,
        "records_found": records_found,
        "valid_values": valid_values,
        "units": units,
        "error": error_message
    })

    # Brief spacing between API requests.
    time.sleep(1)


# SECTION 5: Save results

report = pd.DataFrame(results)

report.to_csv(OUTPUT_FILE, index=False)

print("\n============================")
print("Verification summary")
print("============================")

print(
    report[
        [
            "station_id",
            "status",
            "records_found",
            "valid_values"
        ]
    ].to_string(index=False)
)

print("\nReport saved to:")
print(OUTPUT_FILE)

print("\nVerification test complete!")
