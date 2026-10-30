
from pathlib import Path
import json

import h5py
import numpy as np
import pandas as pd


# SECTION 1: Locate the project

ROOT = Path(__file__).resolve().parent.parent

HDF5_FILE = ROOT / "data/hdf5/dc_flood_data.h5"

OUTPUT_DIR = ROOT / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

INVENTORY_FILE = OUTPUT_DIR / "hdf5_metadata_audit.csv"

SUMMARY_FILE = OUTPUT_DIR / "hdf5_metadata_summary.json"


# SECTION 2: Convert HDF5 values for reporting

def make_readable(value):
    """Convert HDF5 values into JSON-friendly values."""

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")

    if isinstance(value, np.ndarray):
        return [make_readable(x) for x in value.tolist()]

    if isinstance(value, np.generic):
        return make_readable(value.item())

    if isinstance(value, (list, tuple)):
        return [make_readable(x) for x in value]

    if isinstance(value, dict):
        return {
            str(k): make_readable(v)
            for k, v in value.items()
        }

    if isinstance(value, (str, int, float, bool)):
        return value

    if value is None:
        return None

    return str(value)


# SECTION 3: Inspect groups and datasets

records = []

def inspect_item(name, obj):
    """Collect structure and attributes without changing data."""

    if isinstance(obj, h5py.Dataset):
        object_type = "dataset"
        shape = str(obj.shape)
        dtype = str(obj.dtype)
        compression = obj.compression or "none"
        chunks = str(obj.chunks)
    else:
        object_type = "group"
        shape = ""
        dtype = ""
        compression = ""
        chunks = ""

    attributes = {
        str(k): make_readable(v)
        for k, v in obj.attrs.items()
    }

    records.append({
        "path": "/" + name,
        "object_type": object_type,
        "shape": shape,
        "dtype": dtype,
        "compression": compression,
        "chunks": chunks,
        "attributes_json": json.dumps(
            attributes,
            ensure_ascii=False
        )
    })


# SECTION 4: Read the HDF5 structure

if not HDF5_FILE.is_file():
    raise FileNotFoundError(
        f"HDF5 database not found: {HDF5_FILE}"
    )

with h5py.File(HDF5_FILE, "r") as h5:

    database_attributes = {
        str(k): make_readable(v)
        for k, v in h5.attrs.items()
    }

    h5.visititems(inspect_item)

    top_level_groups = list(h5.keys())


# SECTION 5: Save the inventory

inventory = pd.DataFrame(records)

inventory.to_csv(
    INVENTORY_FILE,
    index=False
)

print("=== HDF5 METADATA INVENTORY ===")

print("Top-level groups:", top_level_groups)
print("HDF5 objects inspected:", len(inventory))

print("\nObject types:")
print(
    inventory["object_type"].value_counts()
    .to_string()
)


# SECTION 6: Display selected spatial/temporal fields

keywords = [
    "crs", "epsg", "latitude", "longitude",
    "lat", "lon", "bounds", "resolution",
    "transform", "units", "nodata", "missing",
    "datum", "station", "time", "date",
    "timezone", "interval", "frequency",
    "source", "sampling", "calendar"
]

relevant = inventory[
    inventory["path"].str.lower().str.contains(
        r"precipitation|gauges|events",
        regex=True
    )
].copy()

print("\n=== SAMPLE HDF5 OBJECTS ===")

print(
    relevant[
        ["path", "object_type", "shape", "dtype"]
    ].head(20).to_string(index=False)
)

print("\n=== DATABASE ATTRIBUTES ===")

for key, value in database_attributes.items():
    print(f"{key}: {value}")


# SECTION 7: Search stored attribute names

attribute_counts = {}

for record in records:

    attrs = json.loads(record["attributes_json"])

    for key in attrs:

        key_lower = key.lower()

        if any(word in key_lower for word in keywords):
            attribute_counts[key] = (
                attribute_counts.get(key, 0) + 1
            )

print("\n=== RELEVANT ATTRIBUTE NAMES ===")

for name, count in sorted(attribute_counts.items()):
    print(f"{name}: found on {count} objects")


# SECTION 8: Audit example datasets

examples = {
    "event": "/events/FLOOD_125",
    "precipitation": "/precipitation/20250719",
    "gauge": "/gauges/01648010/FLOOD_125"
}

example_reports = {}

with h5py.File(HDF5_FILE, "r") as h5:

    for label, path in examples.items():

        if path not in h5:
            example_reports[label] = {
                "path": path,
                "found": False
            }
            continue

        obj = h5[path]

        example_reports[label] = {
            "path": path,
            "found": True,
            "type": (
                "dataset" if isinstance(obj, h5py.Dataset)
                else "group"
            ),
            "attributes": {
                str(k): make_readable(v)
                for k, v in obj.attrs.items()
            }
        }

        if isinstance(obj, h5py.Group):
            example_reports[label]["children"] = list(
                obj.keys()
            )


# SECTION 9: Save summary

summary = {
    "database": str(HDF5_FILE),
    "top_level_groups": top_level_groups,
    "database_attributes": database_attributes,
    "object_count": len(inventory),
    "relevant_attribute_counts": attribute_counts,
    "examples": example_reports
}

with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=4)


# SECTION 10: Final output

print("\n=== REPRESENTATIVE OBJECTS ===")

for name, report in example_reports.items():
    print("\n", name.upper())
    print(json.dumps(report, indent=2))

print("\nMetadata inventory saved to:")
print(INVENTORY_FILE)

print("\nMetadata summary saved to:")
print(SUMMARY_FILE)

print("\nMetadata inspection complete!")
