
from pathlib import Path
import pandas as pd

# SECTION 1: Locate project folders

ROOT = Path(__file__).resolve().parent.parent

METADATA_DIR = ROOT / "data" / "metadata"
METADATA_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = METADATA_DIR / "usgs_gauge_inventory.csv"


# SECTION 2: Define monitoring stations

# Coverage dates are from published USGS records.
# These describe broad published availability,
# not a guarantee of observations on every date.

stations = [
    {
        "station_id": "01648000",
        "station_name": "Rock Creek at Sherrill Drive",
        "latitude": 38.972500,
        "longitude": -77.040000,
        "jurisdiction": "DC",
        "variable": "gage height",
        "parameter_code": "00065",
        "units": "ft",
        "start_date": "2007-10-01",
        "end_date": "2026-03-19",
        "notes": "Discontinued; older discharge data exist",
    },
    {
        "station_id": "01648010",
        "station_name": "Rock Creek at Joyce Road",
        "latitude": 38.960167,
        "longitude": -77.042056,
        "jurisdiction": "DC",
        "variable": "gage height",
        "parameter_code": "00065",
        "units": "ft",
        "start_date": "2012-10-01",
        "end_date": "",
        "notes": "Continuous gage-height observations",
    },
    {
        "station_id": "01651827",
        "station_name": "Anacostia River near Buzzard Point",
        "latitude": None,
        "longitude": None,
        "jurisdiction": "DC",
        "variable": "gage height",
        "parameter_code": "00065",
        "units": "ft",
        "start_date": "2019-03-13",
        "end_date": "",
        "notes": "Tidal river; verify station coordinates",
    },
    {
        "station_id": "01651760",
        "station_name": "Anacostia River at Kenilworth",
        "latitude": None,
        "longitude": None,
        "jurisdiction": "DC",
        "variable": "gage height",
        "parameter_code": "00065",
        "units": "ft",
        "start_date": "2024-07-03",
        "end_date": "",
        "notes": "Recent station; verify station coordinates",
    },
]

# SECTION 3: Convert records to a DataFrame

inventory = pd.DataFrame(stations)

inventory["source_url"] = (
    "https://waterdata.usgs.gov/monitoring-location/USGS-"
    + inventory["station_id"]
    + "/"
)

inventory["start_date"] = pd.to_datetime(
    inventory["start_date"]
)

inventory["end_date"] = pd.to_datetime(
    inventory["end_date"]
)

# SECTION 4: Save the station inventory

inventory.to_csv(OUTPUT_FILE, index=False)

# SECTION 5: Print verification results

print("Number of stations:", len(inventory))

print("\nStation inventory:")
print(
    inventory[
        [
            "station_id",
            "station_name",
            "start_date",
            "end_date"
        ]
    ].to_string(index=False)
)

print("\nInventory saved to:")
print(OUTPUT_FILE)

print("\nStation inventory complete!")
