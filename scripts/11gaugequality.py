
from pathlib import Path
import json

import numpy as np
import pandas as pd


# SECTION 1: Locate project folders

ROOT = Path(__file__).resolve().parent.parent

GAUGE_DIR = ROOT / "data" / "processed" / "gauges"
OUTPUT_DIR = ROOT / "outputs"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / "usgs_gauge_quality.csv"


# SECTION 2: Find existing gauge files

gauge_files = sorted(
    GAUGE_DIR.glob("gauge_USGS-*_FLOOD_*.csv")
)

print("Gauge CSV files found:", len(gauge_files))

if not gauge_files:
    raise FileNotFoundError(
        "No gauge CSV files found in data/processed/gauges."
    )


# SECTION 3: Define a function to evaluate one file

def assess_gauge_file(csv_path):

    metadata_path = csv_path.with_name(
        csv_path.stem + "_metadata.json"
    )

    # Load the metadata created by the batch downloader.
    if not metadata_path.exists():
        raise FileNotFoundError(
            f"Missing metadata: {metadata_path.name}"
        )

    with open(metadata_path, encoding="utf-8") as f:
        metadata = json.load(f)

    # Load water-level observations.
    df = pd.read_csv(csv_path)

    required = [
        "station_id",
        "time_utc",
        "gauge_height",
        "unit",
        "approval_status"
    ]

    missing_columns = [
        c for c in required if c not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing columns: {missing_columns}"
        )

    # Convert timestamps and values.
    df["time_utc"] = pd.to_datetime(
        df["time_utc"],
        utc=True,
        errors="coerce"
    )

    df["gauge_height"] = pd.to_numeric(
        df["gauge_height"],
        errors="coerce"
    )

    window_start = pd.to_datetime(
        metadata["window_start_utc"], utc=True
    )

    window_end = pd.to_datetime(
        metadata["window_end_utc"], utc=True
    )

    if window_end <= window_start:
        raise ValueError("Invalid observation window.")

    total_rows = len(df)

    invalid_timestamps = int(
        df["time_utc"].isna().sum()
    )

    valid_heights = int(
        df["gauge_height"].notna().sum()
    )

    missing_heights = int(
        df["gauge_height"].isna().sum()
    )

    # Check station identities and requested time window.
    station_mismatches = int(
        (
            df["station_id"].astype(str)
            != metadata["station_id"]
        ).sum()
    )

    outside_window = int(
        (
            df["time_utc"].notna()
            & (
                (df["time_utc"] < window_start)
                | (df["time_utc"] > window_end)
            )
        ).sum()
    )

    # Keep valid timestamp rows in chronological order.
    timed = df.dropna(
        subset=["time_utc"]
    ).sort_values("time_utc").copy()

    duplicate_timestamps = int(
        timed["time_utc"].duplicated().sum()
    )

    # Multiple readings at the same timestamp may
    # represent different time series or revisions.
    # Preserve them; do not silently discard them.
    unique_times = timed["time_utc"].drop_duplicates()

    first_time = (
        unique_times.iloc[0] if len(unique_times)
        else pd.NaT
    )

    last_time = (
        unique_times.iloc[-1] if len(unique_times)
        else pd.NaT
    )

    # SECTION 4: Calculate sampling intervals

    differences = (
        unique_times.diff()
        .dropna()
        .dt.total_seconds() / 60
    )

    typical_interval = np.nan
    largest_gap = np.nan
    gap_count = 0
    estimated_missing_steps = 0

    if len(differences) > 0:

        # Use the most common interval as a working
        # estimate of the normal sampling frequency.
        typical_interval = float(
            differences.mode().iloc[0]
        )

        largest_gap = float(
            differences.max()
        )

        if typical_interval > 0:

            # A gap is counted when it is substantially
            # longer than the typical sampling interval.
            gap_count = int(
                (differences > 1.5 * typical_interval)
                .sum()
            )

            # Estimate missing scheduled observations
            # between consecutive actual timestamps.
            estimated_missing_steps = int(
                np.maximum(
                    np.rint(
                        differences.to_numpy()
                        / typical_interval
                    ).astype(int) - 1,
                    0
                ).sum()
            )

    # SECTION 5: Check observation-window boundaries

    start_gap_minutes = np.nan
    end_gap_minutes = np.nan

    if pd.notna(first_time):
        start_gap_minutes = max(
            0,
            (first_time - window_start).total_seconds()
            / 60
        )

    if pd.notna(last_time):
        end_gap_minutes = max(
            0,
            (window_end - last_time).total_seconds()
            / 60
        )

    # SECTION 6: Check source quality information

    approval_counts = (
        df["approval_status"]
        .fillna("Unknown")
        .astype(str)
        .value_counts()
        .to_dict()
    )

    units = sorted(
        df["unit"].dropna().astype(str).unique().tolist()
    )

    series_column = (
        "time_series_id"
        if "time_series_id" in df.columns
        else "timeseries_id"
        if "timeseries_id" in df.columns
        else None
    )

    series_ids = (
        sorted(
            df[series_column]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )
        if series_column else []
    )

    # This indicates whether the file needs further
    # review, not whether the data are scientifically
    # correct or a flood occurred.
    issues = []

    if invalid_timestamps:
        issues.append("invalid_timestamps")

    if missing_heights:
        issues.append("missing_height_values")

    if duplicate_timestamps:
        issues.append("duplicate_timestamps")

    if station_mismatches:
        issues.append("station_id_mismatch")

    if outside_window:
        issues.append("out_of_window_records")

    if gap_count:
        issues.append("internal_time_gaps")

    if len(units) != 1 or (units and units[0] != "ft"):
        issues.append("units_need_review")

    if not valid_heights:
        issues.append("no_valid_heights")

    # SECTION 7: Return one summary row

    return {
        "station_id": metadata["station_id"],
        "event_id": metadata["event_id"],
        "file_name": csv_path.name,
        "window_start_utc": window_start.isoformat(),
        "window_end_utc": window_end.isoformat(),
        "first_observation_utc": (
            first_time.isoformat()
            if pd.notna(first_time) else ""
        ),
        "last_observation_utc": (
            last_time.isoformat()
            if pd.notna(last_time) else ""
        ),
        "total_rows": total_rows,
        "valid_heights": valid_heights,
        "missing_heights": missing_heights,
        "invalid_timestamps": invalid_timestamps,
        "duplicate_timestamps": duplicate_timestamps,
        "station_mismatches": station_mismatches,
        "out_of_window_records": outside_window,
        "typical_interval_minutes": typical_interval,
        "largest_interval_minutes": largest_gap,
        "internal_gap_count": gap_count,
        "estimated_missing_internal_steps":
            estimated_missing_steps,
        "start_boundary_gap_minutes": start_gap_minutes,
        "end_boundary_gap_minutes": end_gap_minutes,
        "units": ";".join(units),
        "approval_counts": json.dumps(approval_counts),
        "time_series_ids": ";".join(series_ids),
        "quality_flags": ";".join(issues),
        "review_needed": bool(issues)
    }


# SECTION 8: Analyze all gauge files

results = []
errors = []

for i, file_path in enumerate(gauge_files, start=1):

    print(
        f"Checking {i}/{len(gauge_files)}: "
        f"{file_path.name}"
    )

    try:
        result = assess_gauge_file(file_path)
        results.append(result)

    except Exception as exc:
        print("  ERROR:", exc)
        errors.append({
            "file_name": file_path.name,
            "error": str(exc)
        })


# SECTION 9: Save the reports

quality = pd.DataFrame(results)
quality.to_csv(OUTPUT_FILE, index=False)

error_file = OUTPUT_DIR / "usgs_gauge_quality_errors.csv"

pd.DataFrame(
    errors, columns=["file_name", "error"]
).to_csv(error_file, index=False)


# SECTION 10: Print the final summary

print("\nQuality assessment complete!")

print("Files found:", len(gauge_files))
print("Files assessed:", len(quality))
print("Files with processing errors:", len(errors))

if not quality.empty:

    print("\nTotal valid gauge heights:",
          quality["valid_heights"].sum())

    print("Missing stored heights:",
          quality["missing_heights"].sum())

    print("Files with internal time gaps:",
          (quality["internal_gap_count"] > 0).sum())

    print("Files with duplicate timestamps:",
          (quality["duplicate_timestamps"] > 0).sum())

    print("\nTypical sampling intervals (minutes):")
    print(
        quality["typical_interval_minutes"]
        .value_counts(dropna=False)
    )

    print("\nFiles requiring review:")
    print(
        quality["review_needed"].value_counts()
    )

print("\nQuality report saved to:")
print(OUTPUT_FILE)

print("\nError report saved to:")
print(error_file)
