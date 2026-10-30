
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

DATA_FILE = (
    ROOT / "data/processed/dc_precipitation"
    / "noaa_arboretum_daily.csv"
)

COVERAGE_FILE = (
    ROOT / "outputs/dc_precipitation"
    / "arboretum_event_date_coverage.csv"
)

df = pd.read_csv(DATA_FILE)
coverage = pd.read_csv(COVERAGE_FILE)

print("=== NOAA PRECIPITATION QUALITY REVIEW ===")

print("\nTotal observations:", len(df))
print(
    "Usable precipitation values:",
    df["precipitation_mm"].notna().sum()
)
print(
    "Missing precipitation values:",
    df["precipitation_mm"].isna().sum()
)

print(
    "\nZero rainfall values:",
    (df["precipitation_mm"] == 0).sum()
)

print(
    "\nPositive rainfall values:",
    (df["precipitation_mm"] > 0).sum()
)

print("\n=== PRECIPITATION ATTRIBUTE CODES ===")

if "PRCP_ATTRIBUTES" in df.columns:
    print(
        df["PRCP_ATTRIBUTES"]
        .fillna("(blank)")
        .value_counts()
        .head(20)
        .to_string()
    )

    print("\nExample records with attributes:")
    print(
        df.loc[
            df["PRCP_ATTRIBUTES"].notna(),
            ["date", "precipitation_mm",
             "PRCP_ATTRIBUTES"]
        ].head(15).to_string(index=False)
    )
else:
    print("Attribute column not found.")

print("\n=== MISSING FLOOD-EVENT COVERAGE ===")

missing = coverage.loc[
    ~coverage["precipitation_available"]
]

print(
    missing[
        ["event_id", "event_start_date_fixed_est"]
    ].to_string(index=False)
)

print("\n=== JULY 19, 2025 OBSERVATION ===")

example = df.loc[
    df["date"] == "2025-07-19"
]

print(example.to_string(index=False))

print("\nQuality review complete!")


# SECTION: Compare surrounding precipitation dates

print("\n=== FLOOD_125 SURROUNDING DAYS ===")

df["date"] = pd.to_datetime(df["date"])

surrounding_days = df.loc[
    (df["date"] >= "2025-07-18")
    & (df["date"] <= "2025-07-21"),
    [
        "date",
        "precipitation_mm",
        "PRCP_ATTRIBUTES"
    ]
]

print(surrounding_days.to_string(index=False))


# Summarize the measurement flags used in the dataset

print("\n=== MEASUREMENT FLAGS ===")

attributes = (
    df["PRCP_ATTRIBUTES"]
    .fillna("")
    .astype(str)
    .str.split(",")
)

df["measurement_flag"] = attributes.str[0].fillna("")
df["quality_flag"] = attributes.str[1].fillna("")
df["source_flag"] = attributes.str[2].fillna("")
df["observation_time"] = attributes.str[3].fillna("")

print("\nMeasurement flags:")
print(df["measurement_flag"].value_counts().to_string())

print("\nQuality flags:")
print(
    df["quality_flag"]
    .replace("", "(blank)")
    .value_counts()
    .to_string()
)

print("\nObservation times:")
print(
    df["observation_time"]
    .replace("", "(blank)")
    .value_counts()
    .head(10)
    .to_string()
)

print("\nAdditional station review complete!")