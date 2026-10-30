
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

inventory_path = (
    ROOT / "data/metadata/usgs_gauge_inventory.csv"
)

df = pd.read_csv(
    inventory_path,
    dtype={"station_id": str}
)

# Coordinates verified from official USGS records.
corrections = {
    "01651827": {
        "latitude": 38.86516666666667,
        "longitude": -77.01033333333334
    },
    "01651760": {
        "latitude": 38.909166666666664,
        "longitude": -76.95527777777778
    }
}

assert all(
    (df["station_id"] == sid).sum() == 1
    for sid in corrections
), "Station IDs are missing or duplicated."

for station_id, values in corrections.items():

    mask = df["station_id"] == station_id

    for column, value in values.items():
        df.loc[mask, column] = value

# Preserve verified datum information separately.
df["gage_datum_note"] = ""

for station_id in corrections:
    df.loc[
        df["station_id"] == station_id,
        "gage_datum_note"
    ] = "Gage datum: 0.00 ft above NAVD88 (USGS)"

df["coordinates_source"] = ""

for station_id in corrections:
    df.loc[
        df["station_id"] == station_id,
        "coordinates_source"
    ] = (
        "https://waterdata.usgs.gov/"
        f"monitoring-location/USGS-{station_id}/"
    )

# Save a corrected inventory without overwriting
# the file already embedded in the validated HDF5.
output_path = (
    ROOT / "data/metadata/"
    "usgs_gauge_inventory_corrected.csv"
)

df.to_csv(output_path, index=False)

print("\n=== CORRECTED STATION INVENTORY ===")

print(
    df[
        ["station_id", "station_name",
         "latitude", "longitude",
         "gage_datum_note"]
    ].to_string(index=False)
)

print("\nCorrected inventory saved to:")
print(output_path)