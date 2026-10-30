
from pathlib import Path
from datetime import timezone, timedelta
import json

import h5py
import numpy as np
import pandas as pd

from hdf5_functions import (
    get_flood_event,
    get_precipitation,
    get_gauge_data,
    list_precipitation_dates,
    list_gauge_events
)


# SECTION 1: Locate the database

ROOT = Path(__file__).resolve().parent.parent

HDF5_FILE = (
    ROOT / "data/hdf5/dc_flood_data.h5"
)

FIXED_EST = timezone(timedelta(hours=-5))


# SECTION 2: List available events

def list_flood_events():
    """Return the flood-event IDs stored in HDF5."""

    with h5py.File(HDF5_FILE, "r") as h5:
        ids = h5["events/event_ids"].asstr()[:]

    return list(ids)


# SECTION 3: List sources and variables

def list_data_sources():
    """Describe the assigned sources stored in HDF5."""

    return {
        "PRISM": {
            "group": "/precipitation",
            "variable": "daily precipitation",
            "units": "mm",
            "temporal_resolution": "daily"
        },
        "USGS": {
            "group": "/gauges",
            "variable": "gauge height",
            "units": "ft",
            "temporal_resolution": "station-dependent"
        }
    }


# SECTION 4: List stations

def list_gauge_stations():
    """Return available USGS station identifiers."""

    with h5py.File(HDF5_FILE, "r") as h5:
        stations = sorted(h5["gauges"].keys())

    return stations


# SECTION 5: Describe the HDF5 database

def get_database_metadata():
    """Return database attributes and dataset inventories."""

    def convert(value):
        if isinstance(value, bytes):
            return value.decode("utf-8")
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
        return value

    with h5py.File(HDF5_FILE, "r") as h5:

        attributes = {
            name: convert(value)
            for name, value in h5.attrs.items()
        }

        dates = sorted(
            h5["precipitation"].keys()
        )

        station_ids = sorted(
            h5["gauges"].keys()
        )

    return {
        "attributes": attributes,
        "sources": list_data_sources(),
        "precipitation_date_range": (
            dates[0], dates[-1]
        ) if dates else None,
        "precipitation_date_count": len(dates),
        "stations": station_ids
    }


# SECTION 6: Retrieve event-associated precipitation

def get_event_precipitation(event_id, date=None):
    """
    Retrieve PRISM data for a flood event.

    If date is omitted, use the flood start date
    interpreted in the instructor's fixed EST.

    This selects the matching calendar date only;
    it does not prove temporal accumulation overlap.
    """

    event = get_flood_event(event_id)

    start_utc = pd.to_datetime(
        event["begin_utc"], utc=True
    )

    event_date = (
        start_utc.tz_convert(FIXED_EST)
        .strftime("%Y-%m-%d")
    )

    selected_date = (
        event_date if date is None else date
    )

    rainfall, mask, metadata = (
        get_precipitation(selected_date)
    )

    metadata["event_id"] = event_id
    metadata["event_start_date_fixed_est"] = event_date
    metadata["source"] = "PRISM"
    metadata["date_matching_note"] = (
        "Date selected from the event's fixed-EST "
        "start date. Daily accumulation boundaries "
        "must be evaluated separately."
    )

    return rainfall, mask, metadata


# SECTION 7: Retrieve gauges within a time window

def get_gauge_time_window(
    station_id,
    event_id,
    start_utc=None,
    end_utc=None
):
    """
    Retrieve USGS gauge observations for a chosen
    UTC time window within an event dataset.
    """

    df, metadata = get_gauge_data(
        station_id, event_id
    )

    if start_utc is not None:
        start = pd.to_datetime(
            start_utc, utc=True
        )
        df = df.loc[
            df["time_utc"] >= start
        ]

    if end_utc is not None:
        end = pd.to_datetime(
            end_utc, utc=True
        )
        df = df.loc[
            df["time_utc"] <= end
        ]

    df = df.copy().reset_index(drop=True)

    metadata["filtered_record_count"] = len(df)

    if not df.empty:
        metadata["first_timestamp_utc"] = (
            df["time_utc"].min().isoformat()
        )
        metadata["last_timestamp_utc"] = (
            df["time_utc"].max().isoformat()
        )

    return df, metadata


# SECTION 8: Summarize precipitation availability

def summarize_prism_coverage(event_id):
    """Summarize available PRISM dates for one event."""

    event = get_flood_event(event_id)

    start = pd.to_datetime(
        event["begin_utc"], utc=True
    ).tz_convert(FIXED_EST)

    end = pd.to_datetime(
        event["end_utc"], utc=True
    ).tz_convert(FIXED_EST)

    expected_dates = pd.date_range(
        start=start.date(),
        end=end.date(),
        freq="D"
    ).strftime("%Y%m%d").tolist()

    available = set(
        list_precipitation_dates()
    )

    matched = [
        date for date in expected_dates
        if date in available
    ]

    missing = [
        date for date in expected_dates
        if date not in available
    ]

    return {
        "event_id": event_id,
        "source": "PRISM",
        "requested_dates": len(expected_dates),
        "available_dates": len(matched),
        "missing_dates": missing,
        "coverage_fraction": (
            len(matched) / len(expected_dates)
            if expected_dates else None
        ),
        "note": (
            "Coverage counts stored calendar dates, "
            "not proof of exact accumulation overlap."
        )
    }


# SECTION 9: Summarize gauge availability

def summarize_gauge_coverage(event_id):
    """Summarize stored gauge observations by station."""

    stations = list_gauge_stations()
    records = []

    with h5py.File(HDF5_FILE, "r") as h5:

        for station_id in stations:

            path = f"gauges/{station_id}/{event_id}"

            if path not in h5:
                records.append({
                    "station_id": station_id,
                    "event_id": event_id,
                    "available": False,
                    "observations": 0,
                    "valid_heights": 0
                })
                continue

            group = h5[path]
            heights = group["gauge_height"][:]

            records.append({
                "station_id": station_id,
                "event_id": event_id,
                "available": True,
                "observations": len(heights),
                "valid_heights": int(
                    np.isfinite(heights).sum()
                )
            })

    return pd.DataFrame(records)


# SECTION 10: Combined event coverage summary

def summarize_event_coverage(event_id):
    """Return PRISM and USGS coverage for one event."""

    return {
        "event_id": event_id,
        "prism": summarize_prism_coverage(event_id),
        "gauges": summarize_gauge_coverage(event_id)
    }
