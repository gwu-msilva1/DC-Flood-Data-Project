
from pathlib import Path
from datetime import datetime, timezone
import json

import h5py
import numpy as np
import pandas as pd
import rasterio


# SECTION 1: Locate project directories

ROOT = Path(__file__).resolve().parent.parent

EVENTS_FILE = (
    ROOT / "data/processed/flood_events_cleaned.csv"
)

RASTER_DIR = ROOT / "data/processed/rasters"
GAUGE_DIR = ROOT / "data/processed/gauges"
METADATA_DIR = ROOT / "data/metadata"
OUTPUT_DIR = ROOT / "outputs"

HDF5_DIR = ROOT / "data/hdf5"
HDF5_DIR.mkdir(parents=True, exist_ok=True)


# SECTION 2: Choose test or full database

TEST_MODE = False

if TEST_MODE:
    OUTPUT_FILE = HDF5_DIR / "dc_flood_test.h5"
    MAX_RASTERS = 2
    MAX_GAUGES = 2
else:
    OUTPUT_FILE = HDF5_DIR / "dc_flood_data.h5"
    MAX_RASTERS = None
    MAX_GAUGES = None


# SECTION 3: Helper functions

STRING_TYPE = h5py.string_dtype(encoding="utf-8")


def save_text(group, name, content):
    """Save a UTF-8 text value in HDF5."""
    group.create_dataset(
        name, data=str(content), dtype=STRING_TYPE
    )


def save_strings(group, name, values):
    """Save an array of strings."""
    group.create_dataset(
        name,
        data=np.asarray(
            [str(v) for v in values], dtype=object
        ),
        dtype=STRING_TYPE
    )


def save_json(group, name, obj):
    """Save a dictionary as JSON text."""
    save_text(
        group, name,
        json.dumps(obj, default=str)
    )


def save_source_file(group, name, path):
    """Preserve an original CSV as a text dataset."""
    if path.exists():
        save_text(
            group, name,
            path.read_text(encoding="utf-8-sig")
        )
        return True
    return False


def decode_text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


# SECTION 4: Load input files

events = pd.read_csv(
    EVENTS_FILE, dtype={"event_id": str}
)

raster_files = sorted(
    RASTER_DIR.glob("prism_ppt_800m_*_dc.tif")
)

gauge_files = sorted(
    GAUGE_DIR.glob("gauge_USGS-*_FLOOD_*.csv")
)

print("Flood events:", len(events))
print("PRISM raster files:", len(raster_files))
print("Gauge CSV files:", len(gauge_files))

if events["event_id"].duplicated().any():
    raise ValueError("Duplicate event IDs.")

if len(raster_files) == 0:
    raise FileNotFoundError("No PRISM rasters found.")

if len(gauge_files) == 0:
    raise FileNotFoundError("No gauge CSVs found.")

if MAX_RASTERS is not None:
    raster_files = raster_files[:MAX_RASTERS]

if MAX_GAUGES is not None:
    gauge_files = gauge_files[:MAX_GAUGES]


# SECTION 5: Create the HDF5 database

with h5py.File(OUTPUT_FILE, "w") as h5:

    h5.attrs["project"] = "DC Flood Data Project"
    h5.attrs["database_version"] = "1.0"
    h5.attrs["created_utc"] = datetime.now(
        timezone.utc
    ).isoformat()

    h5.attrs["test_mode"] = TEST_MODE
    h5.attrs["flood_time_convention"] = (
        "Fixed EST, UTC-5, including summer"
    )

    h5.attrs["observation_time_convention"] = "UTC"

    h5.attrs["description"] = (
        "DC flood events with PRISM precipitation "
        "and USGS gauge-height observations."
    )

    # SECTION 6: Save flood event information

    event_group = h5.create_group("events")

    save_source_file(
        event_group, "event_index_csv", EVENTS_FILE
    )

    save_strings(
        event_group, "event_ids",
        events["event_id"].tolist()
    )

    for _, row in events.iterrows():

        event_id = row["event_id"]

        event_subgroup = event_group.create_group(
            event_id
        )

        save_json(
            event_subgroup,
            "record_json",
            row.where(pd.notna(row), None).to_dict()
        )

    print("\nSaved flood events:", len(events))


    # SECTION 7: Save PRISM precipitation rasters

    prism_group = h5.create_group("precipitation")

    prism_group.attrs["source"] = "PRISM Climate Group"
    prism_group.attrs["variable"] = "daily precipitation"
    prism_group.attrs["units"] = "mm"
    prism_group.attrs["nominal_resolution"] = "800m"

    saved_rasters = 0

    for raster_path in raster_files:

        date = raster_path.stem.split("_")[-2]

        date_group = prism_group.create_group(date)

        with rasterio.open(raster_path) as src:

            data = src.read(1, masked=True).astype(
                "float32"
            ).filled(np.nan)

            date_group.create_dataset(
                "values",
                data=data,
                compression="gzip",
                compression_opts=4
            )

            # Save the raster's original affine transform.
            date_group.attrs["transform"] = tuple(
                src.transform
            )

            date_group.attrs["crs"] = str(src.crs)
            date_group.attrs["width"] = src.width
            date_group.attrs["height"] = src.height
            date_group.attrs["source_file"] = raster_path.name

            # Preserve the original grid's geographic
            # coordinate transformation rather than
            # introducing a new interpolation grid.
            date_group.attrs["bounds"] = tuple(src.bounds)
            date_group.attrs["pixel_spacing"] = tuple(src.res)

            # Store a valid-data mask.
            date_group.create_dataset(
                "valid_mask",
                data=np.isfinite(data),
                compression="gzip"
            )

        metadata_path = raster_path.with_name(
            raster_path.stem.replace("_dc", "_metadata")
            + ".json"
        )

        if metadata_path.exists():
            save_text(
                date_group,
                "metadata_json",
                metadata_path.read_text(
                    encoding="utf-8"
                )
            )

        saved_rasters += 1

    print("Saved PRISM rasters:", saved_rasters)


    # SECTION 8: Save USGS gauge observations

    gauges_group = h5.create_group("gauges")

    gauges_group.attrs["source"] = (
        "United States Geological Survey"
    )
    gauges_group.attrs["variable"] = "gage height"
    gauges_group.attrs["parameter_code"] = "00065"
    gauges_group.attrs["units"] = "ft"

    saved_gauges = 0
    saved_observations = 0

    for gauge_path in gauge_files:

        # Example filename:
        # gauge_USGS-01648000_FLOOD_121.csv
        parts = gauge_path.stem.split("_")

        station_id = parts[1].replace("USGS-", "")
        event_id = "_".join(parts[2:])

        station_group = gauges_group.require_group(
            station_id
        )

        event_group = station_group.create_group(
            event_id
        )

        df = pd.read_csv(gauge_path)

        df["time_utc"] = pd.to_datetime(
            df["time_utc"], utc=True, errors="coerce"
        )

        if df["time_utc"].isna().any():
            raise ValueError(
                f"Invalid timestamp: {gauge_path.name}"
            )

        heights = pd.to_numeric(
            df["gauge_height"], errors="coerce"
        ).to_numpy(dtype="float64")

        timestamps = [
            t.isoformat()
            for t in df["time_utc"]
        ]

        save_strings(
            event_group, "time_utc", timestamps
        )

        event_group.create_dataset(
            "gauge_height",
            data=heights,
            compression="gzip",
            compression_opts=4
        )

        # Save source quality fields.
        for column in [
            "unit", "approval_status", "qualifier",
            "time_series_id", "timeseries_id"
        ]:
            if column in df.columns:
                save_strings(
                    event_group, column,
                    df[column].astype("string").fillna("").tolist()
                )

        event_group.attrs["station_id"] = station_id
        event_group.attrs["event_id"] = event_id
        event_group.attrs["units"] = "ft"
        event_group.attrs["source_file"] = gauge_path.name
        event_group.attrs["record_count"] = len(df)

        metadata_path = gauge_path.with_name(
            gauge_path.stem + "_metadata.json"
        )

        if metadata_path.exists():
            save_text(
                event_group,
                "metadata_json",
                metadata_path.read_text(
                    encoding="utf-8"
                )
            )

        saved_gauges += 1
        saved_observations += len(df)

    print("Saved gauge datasets:", saved_gauges)
    print("Saved gauge observations:", saved_observations)


    # SECTION 9: Save metadata and availability reports

    metadata_group = h5.create_group("metadata")

    source_files = {
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

    for name, path in source_files.items():

        was_saved = save_source_file(
            metadata_group, name, path
        )

        if not was_saved:
            print("Optional metadata file not found:", path.name)

    save_json(
        metadata_group,
        "source_notes",
        {
            "precipitation": "PRISM 800m daily precipitation",
            "water_level": "USGS parameter 00065",
            "event_times": "Fixed EST (UTC-5)",
            "gauge_times": "UTC",
            "missing_values": (
                "Original missing readings and time gaps "
                "are not interpolated."
            ),
            "ai_assistance": (
                "ChatGPT assisted with implementation."
            )
        }
    )

    # Save summary counts for verification.
    h5.attrs["event_count"] = len(events)
    h5.attrs["raster_count"] = saved_rasters
    h5.attrs["gauge_dataset_count"] = saved_gauges
    h5.attrs["gauge_observation_count"] = saved_observations


# SECTION 10: Final summary

print("\nHDF5 database created successfully!")
print("File:", OUTPUT_FILE)
print(
    "File size (MB):",
    round(OUTPUT_FILE.stat().st_size / 1e6, 2)
)

print("Test mode:", TEST_MODE)
