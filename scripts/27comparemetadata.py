
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

original_file = (
    ROOT / "data/metadata/usgs_gauge_inventory.csv"
)

corrected_file = (
    ROOT / "data/metadata/usgs_gauge_inventory_corrected.csv"
)

original = pd.read_csv(
    original_file,
    dtype={"station_id": str}
)

corrected = pd.read_csv(
    corrected_file,
    dtype={"station_id": str}
)

print("=== STATION INVENTORY COMPARISON ===")

print("\nOriginal stations:", len(original))
print("Corrected stations:", len(corrected))

print("\nOriginal missing coordinates:")
print(original[["latitude", "longitude"]].isna().sum())

print("\nCorrected missing coordinates:")
print(corrected[["latitude", "longitude"]].isna().sum())

print("\nCorrected station information:")
print(
    corrected[
        ["station_id", "station_name",
         "latitude", "longitude",
         "gage_datum_note"]
    ].to_string(index=False)
)

assert len(original) == len(corrected) == 4
assert corrected["latitude"].notna().all()
assert corrected["longitude"].notna().all()

print("\nStation inventory comparison passed!")
