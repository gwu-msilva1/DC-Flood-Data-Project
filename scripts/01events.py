
from pathlib import Path
import pandas as pd

# SECTION 1: Locate the project files

project_dir = Path(__file__).resolve().parent.parent

input_path = project_dir / "data" / "raw" / "DC_flood_times.csv"
output_dir = project_dir / "data" / "processed"

output_dir.mkdir(parents=True, exist_ok=True)

output_path = output_dir / "flood_events_cleaned.csv"


# SECTION 2: Import and inspect the original CSV

required_columns = [
    "begin_date", "begin_time", "end_date", "end_time"
]

events = pd.read_csv(input_path, dtype="string")

if list(events.columns) != required_columns:
    raise ValueError(
        f"Unexpected columns: {list(events.columns)}"
    )

print("Number of original events:", len(events))
print("\nMissing values:")
print(events.isna().sum())

print("\nDuplicate rows:", events.duplicated().sum())


# SECTION 3: Create unique event IDs

events.insert(
    0,
    "event_id",
    [f"FLOOD_{i:03d}" for i in range(1, len(events) + 1)]
)


# SECTION 4: Combine dates and times using fixed EST

from datetime import timezone, timedelta

# Fixed Eastern Standard Time = UTC-5, all year
fixed_est = timezone(timedelta(hours=-5))

for prefix in ("begin", "end"):

    events[f"{prefix}_local"] = pd.to_datetime(
        events[f"{prefix}_date"] + " " + events[f"{prefix}_time"],
        format="%Y-%m-%d %H:%M",
        errors="coerce"
    )

    # The professor specified fixed EST even in summer.
    events[f"{prefix}_eastern"] = (
        events[f"{prefix}_local"].dt.tz_localize(fixed_est)
    )

    events[f"{prefix}_utc"] = (
        events[f"{prefix}_eastern"].dt.tz_convert("UTC")
    )


# SECTION 5: Validate event timestamps

invalid_format = events[
    ["begin_local", "end_local"]
].isna().any(axis=1)

invalid_order = (
    events["end_local"] < events["begin_local"]
).fillna(False)

events["time_status"] = "ok"

events.loc[
    invalid_format, "time_status"
] = "invalid_date_or_time"

events.loc[
    invalid_order, "time_status"
] = "end_before_begin"


# SECTION 6: Calculate flood-event duration

events["duration_minutes"] = (
    events["end_utc"] - events["begin_utc"]
).dt.total_seconds() / 60


# SECTION 7: Format timestamps for the new CSV

for prefix in ("begin", "end"):

    events[f"{prefix}_local"] = (
        events[f"{prefix}_local"].dt.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )

    events[f"{prefix}_eastern"] = (
        events[f"{prefix}_eastern"].dt.strftime(
            "%Y-%m-%dT%H:%M:%S%z"
        )
    )

    events[f"{prefix}_utc"] = (
        events[f"{prefix}_utc"].dt.strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    )


# SECTION 8: Save the processed data

events.to_csv(output_path, index=False)

print("\nTimestamp validation results:")
print(events["time_status"].value_counts())

print("\nEvents requiring review:")
print(
    events.loc[
        events["time_status"] != "ok",
        [
            "event_id", "begin_date", "begin_time",
            "end_date", "end_time", "time_status"
        ]
    ].to_string(index=False)
)

print("\nFirst five prepared events:")
print(
    events[
        ["event_id", "begin_local", "end_local", "time_status"]
    ].head().to_string(index=False)
)

print("\nCleaned file saved to:")
print(output_path)