
from pathlib import Path
import json

import h5py
import numpy as np
import pandas as pd
import rasterio


# SECTION 1: Locate project files

ROOT = Path(__file__).resolve().parent.parent

HDF5_FILE = ROOT / "data/hdf5/dc_flood_data.h5"

EVENTS_FILE = (
    ROOT / "data/processed/flood_events_cleaned.csv"
)

RASTER_DIR = ROOT / "data/processed/rasters"
GAUGE_DIR = ROOT / "data/processed/gauges"

METADATA_DIR = ROOT / "data/metadata"
OUTPUT_DIR = ROOT / "outputs"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

REPORT_FILE = (
    OUTPUT_DIR / "hdf5_integrity_report.csv"
)

SUMMARY_FILE = (
    OUTPUT_DIR / "hdf5_integrity_summary.json"
)


# SECTION 2: Helper functions

results = []


def record_check(category, item, check, passed, details=""):
    """Save one test result."""

    results.append({
        "category": category,
        "item": str(item),
        "check": check,
        "passed": bool(passed),
        "details": str(details)
    })


def text_value(value):
    """Convert HDF5 text into a Python string."""

    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def same_strings(source, stored):
    """Compare strings while treating missing entries as empty."""

    source_values = (
        pd.Series(source)
        .astype("string")
        .fillna("")
        .astype(str)
        .tolist()
    )

    stored_values = [
        text_value(v) for v in stored
    ]

    return source_values == stored_values


# SECTION 3: Confirm required files exist

if not HDF5_FILE.exists():
    raise FileNotFoundError(HDF5_FILE)

if not EVENTS_FILE.exists():
    raise FileNotFoundError(EVENTS_FILE)

raster_files = sorted(
    RASTER_DIR.glob("prism_ppt_800m_*_dc.tif")
)

gauge_files = sorted(
    GAUGE_DIR.glob("gauge_USGS-*_FLOOD_*.csv")
)

events = pd.read_csv(
    EVENTS_FILE,
    dtype={"event_id": str}
)

print("Source flood events:", len(events))
print("Source PRISM rasters:", len(raster_files))
print("Source gauge files:", len(gauge_files))


# SECTION 4: Open HDF5 for reading only

with h5py.File(HDF5_FILE, "r") as h5:

    required_groups = [
        "events", "precipitation",
        "gauges", "metadata"
    ]

    for name in required_groups:
        record_check(
            "structure", name,
            "top_level_group_exists",
            name in h5
        )

    if not all(name in h5 for name in required_groups):
        raise ValueError(
            "HDF5 is missing a required top-level group."
        )

    # SECTION 5: Verify flood-event index

    event_group = h5["events"]

    source_ids = events["event_id"].astype(str).tolist()

    stored_ids = (
        event_group["event_ids"].asstr()[:].tolist()
    )

    record_check(
        "events", "all",
        "event_ids_match",
        source_ids == stored_ids
    )

    source_event_csv = EVENTS_FILE.read_text(
        encoding="utf-8-sig"
    )

    stored_event_csv = text_value(
        event_group["event_index_csv"][()]
    )

    record_check(
        "events", "all",
        "original_csv_text_matches",
        source_event_csv == stored_event_csv
    )

    stored_event_ids = {
        name for name in event_group.keys()
        if name.startswith("FLOOD_")
    }

    record_check(
        "events", "all",
        "event_group_names_match",
        stored_event_ids == set(source_ids)
    )

    # Compare individual stored event records.
    for _, row in events.iterrows():

        event_id = row["event_id"]

        if event_id not in event_group:
            record_check(
                "events", event_id,
                "individual_record", False,
                "Event group missing"
            )
            continue

        expected_record = row.where(
            pd.notna(row), None
        ).to_dict()

        stored_record = json.loads(
            text_value(
                event_group[event_id]["record_json"][()]
            )
        )

        expected_normalized = json.loads(
            json.dumps(expected_record, default=str)
        )

        record_check(
            "events", event_id,
            "individual_record_matches",
            expected_normalized == stored_record
        )

    print("Checked flood-event index.")


    # SECTION 6: Verify PRISM rasters

    precipitation = h5["precipitation"]

    source_dates = {
        path.stem.split("_")[-2]
        for path in raster_files
    }

    stored_dates = set(precipitation.keys())

    record_check(
        "precipitation", "all",
        "date_inventory_matches",
        source_dates == stored_dates
    )

    for i, raster_path in enumerate(
        raster_files, start=1
    ):

        date = raster_path.stem.split("_")[-2]

        if date not in precipitation:
            record_check(
                "precipitation", date,
                "raster_exists", False
            )
            continue

        stored = precipitation[date]

        with rasterio.open(raster_path) as src:

            original = src.read(
                1, masked=True
            ).astype("float32").filled(np.nan)

            hdf_values = stored["values"][:]

            values_match = (
                original.shape == hdf_values.shape
                and np.array_equal(
                    original,
                    hdf_values,
                    equal_nan=True
                )
            )

            record_check(
                "precipitation", date,
                "rainfall_values_match",
                values_match
            )

            source_mask = np.isfinite(original)

            mask_match = np.array_equal(
                source_mask,
                stored["valid_mask"][:]
            )

            record_check(
                "precipitation", date,
                "valid_mask_matches",
                mask_match
            )

            record_check(
                "precipitation", date,
                "crs_matches",
                str(src.crs) == text_value(
                    stored.attrs["crs"]
                )
            )

            record_check(
                "precipitation", date,
                "transform_matches",
                np.allclose(
                    tuple(src.transform),
                    stored.attrs["transform"],
                    rtol=0,
                    atol=1e-12
                )
            )

            record_check(
                "precipitation", date,
                "bounds_match",
                np.allclose(
                    tuple(src.bounds),
                    stored.attrs["bounds"],
                    rtol=0,
                    atol=1e-12
                )
            )

            record_check(
                "precipitation", date,
                "dimensions_match",
                (
                    src.height == stored.attrs["height"]
                    and src.width == stored.attrs["width"]
                )
            )

        if i % 50 == 0:
            print(
                f"Checked PRISM rasters: "
                f"{i}/{len(raster_files)}"
            )

    print("PRISM raster comparison complete.")


    # SECTION 7: Verify USGS gauge time series

    gauges = h5["gauges"]

    source_pairs = set()

    for i, gauge_path in enumerate(
        gauge_files, start=1
    ):

        parts = gauge_path.stem.split("_")

        station_id = parts[1].replace("USGS-", "")
        event_id = "_".join(parts[2:])

        source_pairs.add((station_id, event_id))

        if (
            station_id not in gauges
            or event_id not in gauges[station_id]
        ):
            record_check(
                "gauges",
                f"{station_id}/{event_id}",
                "dataset_exists",
                False
            )
            continue

        stored = gauges[station_id][event_id]

        df = pd.read_csv(
            gauge_path,
            dtype={"station_id": str}
        )

        source_times = pd.to_datetime(
            df["time_utc"],
            utc=True,
            errors="coerce"
        )

        if source_times.isna().any():
            record_check(
                "gauges",
                f"{station_id}/{event_id}",
                "source_timestamps_valid",
                False
            )
            continue

        expected_times = [
            t.isoformat() for t in source_times
        ]

        stored_times = (
            stored["time_utc"].asstr()[:].tolist()
        )

        record_check(
            "gauges",
            f"{station_id}/{event_id}",
            "utc_timestamps_match",
            expected_times == stored_times
        )

        source_heights = pd.to_numeric(
            df["gauge_height"],
            errors="coerce"
        ).to_numpy(dtype="float64")

        stored_heights = stored["gauge_height"][:]

        heights_match = (
            source_heights.shape == stored_heights.shape
            and np.array_equal(
                source_heights,
                stored_heights,
                equal_nan=True
            )
        )

        record_check(
            "gauges",
            f"{station_id}/{event_id}",
            "gauge_heights_match",
            heights_match
        )

        record_check(
            "gauges",
            f"{station_id}/{event_id}",
            "record_count_matches",
            len(df) == stored.attrs["record_count"]
        )

        record_check(
            "gauges",
            f"{station_id}/{event_id}",
            "station_id_matches",
            (
                stored.attrs["station_id"] == station_id
                and (
                    df["station_id"]
                    == f"USGS-{station_id}"
                ).all()
            )
        )

        # Compare source quality fields.
        for column in [
            "unit", "approval_status", "qualifier",
            "time_series_id", "timeseries_id"
        ]:

            if column not in df.columns:
                continue

            if column not in stored:
                record_check(
                    "gauges",
                    f"{station_id}/{event_id}",
                    f"{column}_matches",
                    False,
                    "Column not stored in HDF5"
                )
                continue

            record_check(
                "gauges",
                f"{station_id}/{event_id}",
                f"{column}_matches",
                same_strings(
                    df[column],
                    stored[column].asstr()[:]
                )
            )

        # Compare saved JSON metadata with its source.
        metadata_path = gauge_path.with_name(
            gauge_path.stem + "_metadata.json"
        )

        if metadata_path.exists():

            record_check(
                "gauges",
                f"{station_id}/{event_id}",
                "metadata_json_matches",
                (
                    "metadata_json" in stored
                    and metadata_path.read_text(
                        encoding="utf-8"
                    ) == text_value(
                        stored["metadata_json"][()]
                    )
                ) if "metadata_json" in stored
                else False
            )

        if i % 25 == 0:
            print(
                f"Checked gauge files: "
                f"{i}/{len(gauge_files)}"
            )

    stored_pairs = {
        (station_id, event_id)
        for station_id in gauges.keys()
        for event_id in gauges[station_id].keys()
    }

    record_check(
        "gauges", "all",
        "station_event_inventory_matches",
        source_pairs == stored_pairs
    )

    print("USGS gauge comparison complete.")


    # SECTION 8: Verify supporting CSV metadata

    metadata = h5["metadata"]

    source_reports = {
        "station_inventory_csv":
            METADATA_DIR / "usgs_gauge_inventory.csv",
        "prism_availability_csv":
            OUTPUT_DIR / "prism_availability_800m.csv",
        "prism_event_coverage_csv":
            OUTPUT_DIR / "prism_event_coverage_800m.csv",
        "prism_requested_dates_csv":
            OUTPUT_DIR / "prism_requested_dates.csv",
        "gauge_availability_csv":
            OUTPUT_DIR / "usgs_gauge_availability.csv",
        "gauge_quality_csv":
            OUTPUT_DIR / "usgs_gauge_quality.csv",
        "gauge_verification_csv":
            OUTPUT_DIR / "usgs_gauge_verification.csv"
    }

    for name, path in source_reports.items():

        if not path.exists():
            record_check(
                "metadata", name,
                "source_exists", False
            )
            continue

        if name not in metadata:
            record_check(
                "metadata", name,
                "stored_in_hdf5", False
            )
            continue

        record_check(
            "metadata", name,
            "csv_text_matches",
            path.read_text(
                encoding="utf-8-sig"
            ) == text_value(metadata[name][()])
        )

    print("Supporting metadata comparison complete.")


# SECTION 9: Save the integrity report

report = pd.DataFrame(results)

report.to_csv(REPORT_FILE, index=False)

summary = {
    "database_file": str(HDF5_FILE),
    "total_checks": int(len(report)),
    "passed_checks": int(report["passed"].sum()),
    "failed_checks": int((~report["passed"]).sum()),
    "source_events": int(len(events)),
    "source_rasters": int(len(raster_files)),
    "source_gauge_files": int(len(gauge_files))
}

with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=4)


# SECTION 10: Print results

print("\nHDF5 integrity validation complete!")

print("Total checks:", summary["total_checks"])
print("Passed checks:", summary["passed_checks"])
print("Failed checks:", summary["failed_checks"])

if summary["failed_checks"] > 0:

    print("\nChecks requiring investigation:")

    print(
        report.loc[
            ~report["passed"],
            ["category", "item", "check", "details"]
        ].to_string(index=False)
    )

else:
    print(
        "\nAll implemented source-to-HDF5 "
        "integrity checks passed!"
    )

print("\nReport saved to:", REPORT_FILE)
print("Summary saved to:", SUMMARY_FILE)
