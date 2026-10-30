
from pathlib import Path

import h5py
import numpy as np


# SECTION 1: Locate the database

ROOT = Path(__file__).resolve().parent.parent

TEST_MODE = False

if TEST_MODE:
    HDF5_FILE = ROOT / "data/hdf5/dc_flood_test.h5"
else:
    HDF5_FILE = ROOT / "data/hdf5/dc_flood_data.h5"


# SECTION 2: Open the database

with h5py.File(HDF5_FILE, "r") as h5:

    print("Database:", HDF5_FILE.name)

    print("\nTop-level groups:")
    print(list(h5.keys()))

    print("\nDatabase attributes:")

    for key, value in h5.attrs.items():
        print(f"{key}: {value}")

    # SECTION 3: Check flood events

    events = h5["events"]

    event_ids = events["event_ids"].asstr()[:]

    print("\nFlood events stored:", len(event_ids))
    print("First five event IDs:", event_ids[:5])


    # SECTION 4: Check PRISM precipitation

    precipitation = h5["precipitation"]

    dates = sorted(precipitation.keys())

    print("\nPRISM dates stored:", len(dates))

    first_date = dates[0]
    first_raster = precipitation[first_date]

    values = first_raster["values"][:]
    valid_mask = first_raster["valid_mask"][:]

    print("First PRISM date:", first_date)
    print("Raster shape:", values.shape)
    print("CRS:", first_raster.attrs["crs"])
    print(
        "Pixel spacing:",
        first_raster.attrs["pixel_spacing"]
    )
    print("Valid raster cells:", int(valid_mask.sum()))
    print("Missing raster cells:", int((~valid_mask).sum()))

    if np.isfinite(values).any():
        print("Minimum rainfall (mm):", np.nanmin(values))
        print("Maximum rainfall (mm):", np.nanmax(values))


    # SECTION 5: Check gauge measurements

    gauges = h5["gauges"]

    station_ids = sorted(gauges.keys())

    print("\nGauge stations stored:", station_ids)

    total_gauge_files = sum(
        len(gauges[station_id])
        for station_id in station_ids
    )

    print("Gauge datasets stored:", total_gauge_files)

    first_station = station_ids[0]
    first_event = sorted(
        gauges[first_station].keys()
    )[0]

    dataset = gauges[first_station][first_event]

    timestamps = dataset["time_utc"].asstr()[:]
    heights = dataset["gauge_height"][:]

    print("\nExample gauge dataset:")
    print("Station:", first_station)
    print("Event:", first_event)
    print("Observations:", len(heights))
    print("First timestamp:", timestamps[0])

    print(
        "Valid height measurements:",
        int(np.isfinite(heights).sum())
    )

    print(
        "Minimum gauge height (ft):",
        np.nanmin(heights)
    )

    print(
        "Maximum gauge height (ft):",
        np.nanmax(heights)
    )


    # SECTION 6: Check supporting metadata

    metadata = h5["metadata"]

    print("\nStored metadata files:")
    print(list(metadata.keys()))


print("\nHDF5 verification completed!")
