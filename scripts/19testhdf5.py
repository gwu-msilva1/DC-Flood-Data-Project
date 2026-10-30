
from pathlib import Path
import json

import numpy as np
import pandas as pd

from hdf5_functions import (
    get_flood_event,
    get_precipitation,
    get_gauge_data,
    list_precipitation_dates,
    list_gauge_events
)


# SECTION 1: Project folders

ROOT = Path(__file__).resolve().parent.parent

OUTPUT_DIR = ROOT / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

REPORT_FILE = (
    OUTPUT_DIR / "hdf5_reusability_tests.csv"
)

SUMMARY_FILE = (
    OUTPUT_DIR / "hdf5_reusability_summary.json"
)

results = []


# SECTION 2: Store each test result

def record_test(name, passed, details=""):

    results.append({
        "test": name,
        "passed": bool(passed),
        "details": str(details)
    })

    result = "PASS" if passed else "FAIL"

    print(f"{result}: {name}")

    if details:
        print(" ", details)


# SECTION 3: Test a historical flood event

print("\n=== TEST 1: HISTORICAL EVENT ===")

try:
    event = get_flood_event("FLOOD_039")

    passed = event["event_id"] == "FLOOD_039"

    record_test(
        "Historical flood event retrieval",
        passed,
        f"Retrieved event: {event['event_id']}"
    )

except Exception as exc:
    record_test(
        "Historical flood event retrieval",
        False,
        str(exc)
    )


# SECTION 4: Test historical gauge observations

print("\n=== TEST 2: HISTORICAL GAUGE ===")

try:
    gauge, metadata = get_gauge_data(
        "01648000", "FLOOD_039"
    )

    valid = int(
        gauge["gauge_height"].notna().sum()
    )

    passed = (
        len(gauge) > 0
        and valid > 0
        and metadata["station_id"] == "01648000"
    )

    record_test(
        "Historical gauge retrieval",
        passed,
        f"Rows: {len(gauge)}, valid heights: {valid}"
    )

except Exception as exc:
    record_test(
        "Historical gauge retrieval",
        False,
        str(exc)
    )


# SECTION 5: Test multiple gauge stations

print("\n=== TEST 3: MULTIPLE STATIONS ===")

test_stations = [
    ("01648010", "Joyce Road"),
    ("01651827", "Buzzard Point"),
    ("01651760", "Kenilworth")
]

for station_id, station_name in test_stations:

    try:
        gauge, metadata = get_gauge_data(
            station_id, "FLOOD_125"
        )

        passed = (
            len(gauge) > 0
            and gauge["gauge_height"].notna().any()
            and metadata["station_id"] == station_id
        )

        record_test(
            f"Station retrieval: {station_name}",
            passed,
            f"Observations: {len(gauge)}"
        )

    except Exception as exc:
        record_test(
            f"Station retrieval: {station_name}",
            False,
            str(exc)
        )


# SECTION 6: Test missing-data handling

print("\n=== TEST 4: UNAVAILABLE GAUGE DATA ===")

try:
    get_gauge_data("01651760", "FLOOD_001")

    record_test(
        "Unavailable station-event handling",
        False,
        "Expected an unavailable-data exception."
    )

except ValueError as exc:

    record_test(
        "Unavailable station-event handling",
        True,
        f"Expected error handled: {exc}"
    )

except Exception as exc:

    record_test(
        "Unavailable station-event handling",
        False,
        f"Unexpected exception type: {exc}"
    )


# SECTION 7: Test precipitation retrieval

print("\n=== TEST 5: HISTORICAL PRISM RASTER ===")

try:
    rainfall, mask, metadata = get_precipitation(
        "1996-01-18"
    )

    passed = (
        rainfall.shape == mask.shape
        and mask.any()
        and np.isfinite(rainfall[mask]).all()
        and metadata["date"] == "19960118"
    )

    record_test(
        "Historical PRISM retrieval",
        passed,
        f"Shape: {rainfall.shape}, "
        f"valid cells: {int(mask.sum())}"
    )

except Exception as exc:
    record_test(
        "Historical PRISM retrieval",
        False,
        str(exc)
    )


# SECTION 8: Test available-date inventory

print("\n=== TEST 6: PRISM DATE INVENTORY ===")

try:
    dates = list_precipitation_dates()

    record_test(
        "PRISM date inventory",
        len(dates) == 372,
        f"Dates found: {len(dates)}"
    )

except Exception as exc:
    record_test(
        "PRISM date inventory",
        False,
        str(exc)
    )


# SECTION 9: Test station-event inventory

print("\n=== TEST 7: GAUGE EVENT INVENTORY ===")

try:
    events = list_gauge_events("01651760")

    record_test(
        "Kenilworth event inventory",
        len(events) == 3,
        f"Events found: {len(events)}"
    )

except Exception as exc:
    record_test(
        "Kenilworth event inventory",
        False,
        str(exc)
    )


# SECTION 10: Save testing results

report = pd.DataFrame(results)

report.to_csv(REPORT_FILE, index=False)

summary = {
    "total_tests": len(report),
    "passed_tests": int(report["passed"].sum()),
    "failed_tests": int((~report["passed"]).sum()),
    "database": "data/hdf5/dc_flood_data.h5"
}

with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=4)


# SECTION 11: Final summary

print("\n================================")
print("HDF5 REUSABILITY TEST SUMMARY")
print("================================")

print("Total tests:", summary["total_tests"])
print("Passed:", summary["passed_tests"])
print("Failed:", summary["failed_tests"])

print("\nReport saved to:")
print(REPORT_FILE)

print("\nSummary saved to:")
print(SUMMARY_FILE)

if summary["failed_tests"] == 0:
    print("\nAll reusability tests passed!")
else:
    print("\nSome tests require investigation.")
