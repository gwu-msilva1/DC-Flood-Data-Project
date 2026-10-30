
from pathlib import Path
from datetime import datetime, timezone
from tempfile import TemporaryDirectory
from zipfile import ZipFile, is_zipfile
import json
import shutil
import time

import numpy as np
import pandas as pd
import requests
import rasterio
from rasterio.windows import from_bounds, Window
from rasterio.warp import transform_bounds


# SECTION 1: Set up folders and settings

project_dir = Path(__file__).resolve().parent.parent

events_path = (
    project_dir / "data" / "processed" /
    "flood_events_cleaned.csv"
)

raster_dir = (
    project_dir / "data" / "processed" / "rasters"
)

report_dir = project_dir / "outputs"

raster_dir.mkdir(parents=True, exist_ok=True)
report_dir.mkdir(parents=True, exist_ok=True)

# Start with the resolution we have already tested.
RESOLUTION = "800m"

# TEST: Process only the first 3 dates.
# Later we can increase or remove this limit.
MAX_DATES = 5

# One additional calendar day on each side.
BUFFER_DAYS = 1

# Bounding box around Washington, DC
WEST = -77.20
SOUTH = 38.78
EAST = -76.85
NORTH = 39.02


# SECTION 2: Read flood events

events = pd.read_csv(events_path)

print("Number of flood events:", len(events))

if events["event_id"].duplicated().any():
    raise ValueError("Duplicate event IDs found.")

# These are the original reported EST dates.
events["begin_date"] = pd.to_datetime(
    events["begin_date"], errors="raise"
)

events["end_date"] = pd.to_datetime(
    events["end_date"], errors="raise"
)


# SECTION 3: Build a list of requested dates

date_to_events = {}

for row in events.itertuples(index=False):

    first_day = row.begin_date - pd.Timedelta(
        days=BUFFER_DAYS
    )

    last_day = row.end_date + pd.Timedelta(
        days=BUFFER_DAYS
    )

    for day in pd.date_range(first_day, last_day):

        date_string = day.strftime("%Y%m%d")

        if date_string not in date_to_events:
            date_to_events[date_string] = set()

        date_to_events[date_string].add(row.event_id)

all_dates = sorted(date_to_events)

print("Unique requested dates:", len(all_dates))

# Save the complete date inventory before downloading.
inventory = []

for date_string in all_dates:
    inventory.append({
        "date": date_string,
        "event_ids": ";".join(
            sorted(date_to_events[date_string])
        )
    })

inventory_path = (
    report_dir / "prism_requested_dates.csv"
)

pd.DataFrame(inventory).to_csv(
    inventory_path, index=False
)

# Choose a small test batch.
dates_to_process = (
    all_dates[:MAX_DATES]
    if MAX_DATES is not None
    else all_dates
)

print("Dates selected for this run:",
      len(dates_to_process))


# SECTION 4: Function to download and crop a raster

def process_prism_date(date_string):

    url = (
        "https://services.nacse.org/prism/data/get/"
        f"us/{RESOLUTION}/ppt/{date_string}"
    )

    output_path = (
        raster_dir /
        f"prism_ppt_{RESOLUTION}_{date_string}_dc.tif"
    )

    metadata_path = (
        raster_dir /
        f"prism_ppt_{RESOLUTION}_{date_string}_metadata.json"
    )

    # Do not download dates already processed.
    if output_path.exists() and metadata_path.exists():
        print("Already processed:", date_string)
        return "existing", ""

    # Temporary files are deleted after processing.
    with TemporaryDirectory() as temp_folder:

        temp_dir = Path(temp_folder)
        zip_path = temp_dir / "prism.zip"

        # Download the full source archive.
        with requests.get(
            url, stream=True, timeout=(30, 180)
        ) as response:

            response.raise_for_status()

            with open(zip_path, "wb") as f:
                for chunk in response.iter_content(
                    chunk_size=1024 * 1024
                ):
                    if chunk:
                        f.write(chunk)

        if not is_zipfile(zip_path):
            raise ValueError("Response was not a ZIP file.")

        # Find the GeoTIFF inside the archive.
        with ZipFile(zip_path) as archive:

            tif_names = [
                name for name in archive.namelist()
                if name.lower().endswith(".tif")
                and not name.startswith("__MACOSX/")
            ]

            if len(tif_names) != 1:
                raise ValueError(
                    f"Expected one GeoTIFF, found {len(tif_names)}"
                )

            tif_name = tif_names[0]
            source_path = temp_dir / "source.tif"

            # Extract only the GeoTIFF needed for processing.
            with archive.open(tif_name) as source:
                with open(source_path, "wb") as target:
                    shutil.copyfileobj(source, target)

        # Crop without changing the native grid.
        with rasterio.open(source_path) as src:

            if src.crs is None:
                raise ValueError("Raster has no CRS.")

            bounds = transform_bounds(
                "EPSG:4326", src.crs,
                WEST, SOUTH, EAST, NORTH
            )

            window = from_bounds(
                *bounds, transform=src.transform
            )

            window = window.round_offsets().round_lengths()

            window = window.intersection(
                Window(0, 0, src.width, src.height)
            )

            data = src.read(
                1, window=window, masked=True
            )

            if data.size == 0:
                raise ValueError("No cells in study area.")

            clean_data = data.astype(
                "float32"
            ).filled(np.nan)

            profile = src.profile.copy()

            profile.update(
                driver="GTiff",
                height=clean_data.shape[0],
                width=clean_data.shape[1],
                count=1,
                dtype="float32",
                transform=src.window_transform(window),
                nodata=np.nan,
                compress="deflate"
            )

            source_crs = str(src.crs)
            source_resolution = list(src.res)
            source_nodata = src.nodata

        # Save the cropped raster.
        with rasterio.open(
            output_path, "w", **profile
        ) as dst:
            dst.write(clean_data, 1)

        # Count valid and missing cells.
        total_cells = int(clean_data.size)
        valid_cells = int(
            np.isfinite(clean_data).sum()
        )

        # Record essential metadata.
        metadata = {
            "source": "PRISM Climate Group",
            "variable": "daily precipitation",
            "units": "mm",
            "date": date_string,
            "event_ids": sorted(
                date_to_events[date_string]
            ),
            "resolution_product": RESOLUTION,
            "crs": source_crs,
            "native_resolution": source_resolution,
            "source_nodata": source_nodata,
            "study_bbox_lonlat": [
                WEST, SOUTH, EAST, NORTH
            ],
            "temporal_resolution": "daily",
            "day_boundary": "Requires source verification",
            "download_url": url,
            "retrieved_at_utc": datetime.now(
                timezone.utc
            ).isoformat(),
            "total_cells": total_cells,
            "valid_cells": valid_cells,
            "missing_cells": total_cells - valid_cells,
            "missing_fraction": (
                (total_cells - valid_cells) / total_cells
            ),
            "output_file": output_path.name
        }

        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=4)

    return "success", ""


# SECTION 5: Process dates and record results

report_path = (
    report_dir /
    f"prism_availability_{RESOLUTION}.csv"
)

# Preserve results from previous runs.
if report_path.exists():
    old_report = pd.read_csv(
        report_path, dtype={"date": str}
    )
    results = old_report.set_index(
        "date"
    ).to_dict("index")
else:
    results = {}

for index, date_string in enumerate(
    dates_to_process, start=1
):

    print(
        f"\nProcessing {index}/{len(dates_to_process)}: "
        f"{date_string}"
    )

    try:
        status, error = process_prism_date(
            date_string
        )

        print("Result:", status)

    except Exception as exc:
        status = "failed"
        error = str(exc)
        print("Failed:", error)

    results[date_string] = {
        "status": status,
        "error": error,
        "event_ids": ";".join(
            sorted(date_to_events[date_string])
        ),
        "resolution": RESOLUTION
    }

    # Save after each date so progress is preserved.
    report = pd.DataFrame.from_dict(
        results, orient="index"
    )

    report.index.name = "date"
    report.sort_index().to_csv(report_path)

    if status == "success":
        time.sleep(1)


# SECTION 6: Final summary

print("\nBatch processing complete!")
print("Attempted dates in this run:",
      len(dates_to_process))

report = pd.read_csv(report_path)

print("\nRecorded status counts:")
print(report["status"].value_counts())

print("\nAvailability report:")
print(report_path)

print("\nRequested-date inventory:")
print(inventory_path)
