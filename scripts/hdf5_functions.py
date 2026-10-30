
from pathlib import Path
import json

import h5py
import numpy as np
import pandas as pd


# SECTION 1: Locate the HDF5 database

ROOT = Path(__file__).resolve().parent.parent

HDF5_FILE = (
    ROOT / "data" / "hdf5" / "dc_flood_data.h5"
)


# SECTION 2: Retrieve a flood event

def get_flood_event(event_id):
    """
    Retrieve information about one flood event.

    Example:
        get_flood_event("FLOOD_125")
    """

    with h5py.File(HDF5_FILE, "r") as h5:

        path = f"events/{event_id}/record_json"

        if path not in h5:
            raise ValueError(
                f"Flood event not found: {event_id}"
            )

        record_text = h5[path].asstr()[()]

        event = json.loads(record_text)

    return event


# SECTION 3: Retrieve PRISM precipitation

def get_precipitation(date):
    """
    Retrieve PRISM precipitation for one date.

    Accepted formats:
        "2025-07-19"
        "20250719"
    """

    date_key = pd.to_datetime(
        date, format="mixed"
    ).strftime("%Y%m%d")

    with h5py.File(HDF5_FILE, "r") as h5:

        path = f"precipitation/{date_key}"

        if path not in h5:
            raise ValueError(
                f"No PRISM raster stored for {date_key}"
            )

        group = h5[path]

        rainfall = group["values"][:]

        mask = group["valid_mask"][:]

        crs = group.attrs["crs"]

        bounds = tuple(group.attrs["bounds"])

        transform = tuple(
            group.attrs["transform"]
        )

        metadata = {
            "date": date_key,
            "crs": str(crs),
            "bounds": bounds,
            "transform": transform,
            "units": "mm",
            "shape": rainfall.shape
        }

    return rainfall, mask, metadata


# SECTION 4: Retrieve USGS water-level observations

def get_gauge_data(station_id, event_id):
    """
    Retrieve gauge-height observations for one
    station and flood event.

    Example:
        get_gauge_data("01648010", "FLOOD_125")
    """

    station_id = str(station_id).replace(
        "USGS-", ""
    )

    with h5py.File(HDF5_FILE, "r") as h5:

        path = f"gauges/{station_id}/{event_id}"

        if path not in h5:
            raise ValueError(
                "No gauge dataset stored for "
                f"{station_id} / {event_id}"
            )

        group = h5[path]

        times = group["time_utc"].asstr()[:]

        heights = group["gauge_height"][:]

        data = {
            "time_utc": pd.to_datetime(
                times, utc=True
            ),
            "gauge_height": heights
        }

        # Add source quality information when present.
        for column in [
            "unit",
            "approval_status",
            "qualifier",
            "time_series_id",
            "timeseries_id"
        ]:
            if column in group:
                data[column] = (
                    group[column].asstr()[:]
                )

        df = pd.DataFrame(data)

        df["time_dc"] = (
            df["time_utc"]
            .dt.tz_convert("America/New_York")
        )

        df = df.sort_values(
            "time_utc"
        ).reset_index(drop=True)

        metadata = {
            "station_id": station_id,
            "event_id": event_id,
            "units": str(group.attrs["units"]),
            "record_count": int(
                group.attrs["record_count"]
            )
        }

    return df, metadata


# SECTION 5: List available PRISM dates

def list_precipitation_dates():
    """
    Return all available PRISM dates.
    """

    with h5py.File(HDF5_FILE, "r") as h5:

        dates = sorted(
            h5["precipitation"].keys()
        )

    return dates


# SECTION 6: List available gauge events

def list_gauge_events(station_id):
    """
    Return events with stored gauge data
    at a given station.
    """

    station_id = str(station_id).replace(
        "USGS-", ""
    )

    with h5py.File(HDF5_FILE, "r") as h5:

        path = f"gauges/{station_id}"

        if path not in h5:
            raise ValueError(
                f"Station not found: {station_id}"
            )

        events = sorted(
            h5[path].keys()
        )

    return events
