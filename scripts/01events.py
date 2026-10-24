
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


# SECTION 4: Combine dates and times

for prefix in ("begin", "end"):

    events[f"{prefix}_local"] = pd.to_datetime(
        events[f"{prefix}_date"] + " " + events[f"{prefix}_time"],
        format="%Y-%m-%d %H:%M",
        errors="coerce"
    )

    # Interpret local times using Eastern Time.
    # Ambiguous or nonexistent clock times are flagged
    # rather than silently changed.

    events[f"{prefix}_eastern"] = (
        events[f"{prefix}_local"].dt.tz_localize(
            "America/New_York",
            ambiguous="NaT",
            nonexistent="NaT"
        )
    )

    # Convert valid Eastern timestamps to UTC.
    events[f"{prefix}_utc"] = (
        events[f"{prefix}_eastern"].dt.tz_convert("UTC")
    )


# SECTION 5: Check timestamps and flag problems

invalid_format = events[
    ["begin_local", "end_local"]
].isna().any(axis=1)

invalid_order = (
    events["end_local"] < events["begin_local"]
).fillna(False)

dst_review = (
    events[["begin_eastern", "end_eastern"]]
    .isna().any(axis=1) & ~invalid_format
)

events["time_status"] = "ok"

events.loc[
    invalid_format, "time_status"
] = "invalid_date_or_time"

events.loc[
    invalid_order, "time_status"
] = "end_before_begin"

events.loc[
    dst_review, "time_status"
] = "daylight_saving_review"


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