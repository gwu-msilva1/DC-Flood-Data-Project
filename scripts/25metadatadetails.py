
from pathlib import Path
import json
import h5py
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
H5_PATH = ROOT / "data/hdf5/dc_flood_data.h5"
STATION_FILE = ROOT / "data/metadata/usgs_gauge_inventory.csv"

def show_json_dataset(h5, path):
    print(f"\n=== {path} ===")

    if path not in h5:
        print("Not found in HDF5")
        return

    ds = h5[path]

    if not isinstance(ds, h5py.Dataset):
        print("Path is a group, not a dataset")
        return

    raw = ds[()]

    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")

    try:
        record = json.loads(raw)
        print(json.dumps(record, indent=2, default=str))
    except (TypeError, ValueError):
        print(str(raw)[:4000])


with h5py.File(H5_PATH, "r") as h5:

    # Example flood event
    show_json_dataset(
        h5, "events/FLOOD_125/record_json"
    )

    # Example PRISM raster metadata
    show_json_dataset(
        h5, "precipitation/20250719/metadata_json"
    )

    # Example USGS monitoring station
    show_json_dataset(
        h5,
        "gauges/01648010/FLOOD_125/metadata_json"
    )

    # Supporting metadata inventory
    print("\n=== STORED METADATA FILES ===")
    if "metadata" in h5:
        print(list(h5["metadata"].keys()))


print("\n=== USGS STATION INVENTORY ===")

if STATION_FILE.exists():
    stations = pd.read_csv(
        STATION_FILE,
        dtype={"station_id": str}
    )

    print("\nColumns:")
    print(list(stations.columns))

    print("\nStation information:")
    print(stations.to_string(index=False))
else:
    print("Station inventory file not found")


print("\nDetailed metadata inspection complete!")
