
from pathlib import Path
from datetime import datetime, timezone
import json
import zipfile

import numpy as np
import pandas as pd
import requests
import rasterio

from rasterio.windows import from_bounds, Window
from rasterio.warp import transform_bounds


# SECTION 1: Set up folders

project_dir = Path(__file__).resolve().parent.parent

download_dir = project_dir / "data" / "raw" / "downloads"
raster_dir = project_dir / "data" / "processed" / "rasters"

download_dir.mkdir(parents=True, exist_ok=True)
raster_dir.mkdir(parents=True, exist_ok=True)


# SECTION 2: Choose the flood event

events = pd.read_csv(
    project_dir / "data" / "processed" /
    "flood_events_cleaned.csv"
)

event = events.loc[events["event_id"] == "FLOOD_125"]

if len(event) != 1:
    raise ValueError("FLOOD_125 was not found uniquely.")

event_date = pd.to_datetime(
    event.iloc[0]["begin_date"]
)

date_string = event_date.strftime("%Y%m%d")

print("Selected event:", event.iloc[0]["event_id"])
print("Event date:", event_date.date())


# SECTION 3: Define PRISM download URL

resolution = "4km"

url = (
    "https://services.nacse.org/prism/data/get/"
    f"us/{resolution}/ppt/{date_string}"
)

zip_path = download_dir / f"prism_ppt_{date_string}.zip"

print("\nPRISM URL:", url)

if not zip_path.exists():
    print("Downloading precipitation data...")

    with requests.get(
        url,
        stream=True,
        timeout=(30, 180)
    ) as response:

        response.raise_for_status()

        with open(zip_path, "wb") as f:
            for chunk in response.iter_content(
                chunk_size=1024 * 1024
            ):
                if chunk:
                    f.write(chunk)

else:
    print("Using previously downloaded ZIP file.")

if not zipfile.is_zipfile(zip_path):
    raise ValueError(
        "Downloaded file is not a valid ZIP archive. "
        "Check the PRISM service response."
    )

print("Download file:", zip_path)


# SECTION 4: Extract raster files

extract_dir = download_dir / f"prism_{date_string}"
extract_dir.mkdir(parents=True, exist_ok=True)

with zipfile.ZipFile(zip_path) as archive:

    print("\nArchive contents:")

    for name in archive.namelist():
        print(" ", name)

    allowed_extensions = (
        ".tif", ".bil", ".hdr", ".prj",
        ".stx", ".xml", ".txt", ".csv"
    )

    for member in archive.infolist():

        name = Path(member.filename).name

        if (
            member.is_dir()
            or not name
            or not name.lower().endswith(allowed_extensions)
        ):
            continue

        destination = extract_dir / name

        with archive.open(member) as source:
            with destination.open("wb") as target:
                import shutil
                shutil.copyfileobj(source, target)


# Look for GeoTIFF files first
raster_files = list(extract_dir.glob("*.tif"))

# If no GeoTIFF exists, check for BIL files
if not raster_files:
    raster_files = list(extract_dir.glob("*.bil"))

if len(raster_files) != 1:
    raise ValueError(
        f"Expected one raster, found {len(raster_files)}"
    )

source_raster = raster_files[0]

print("\nRaster extracted:", source_raster.name)


# SECTION 5: Define our study area

# Bounding box in longitude and latitude:
# west, south, east, north
# Includes Washington, DC and a small surrounding area.

west = -77.20
south = 38.78
east = -76.85
north = 39.02


# SECTION 6: Crop the raster to DC

output_raster = (
    raster_dir /
    f"prism_ppt_{resolution}_{date_string}_dc.tif"
)

with rasterio.open(source_raster) as src:

    print("\nOriginal raster metadata:")
    print("CRS:", src.crs)
    print("Resolution:", src.res)
    print("Raster dimensions:", src.width, src.height)
    print("NoData value:", src.nodata)

    if src.crs is None:
        raise ValueError("Source raster has no CRS.")

    # Convert our latitude/longitude bounds
    # into the raster's coordinate system.

    projected_bounds = transform_bounds(
        "EPSG:4326",
        src.crs,
        west, south, east, north
    )

    # Identify raster cells intersecting our region.
    window = from_bounds(
        *projected_bounds,
        transform=src.transform
    )

    window = window.round_offsets().round_lengths()

    full_window = Window(
        0, 0, src.width, src.height
    )

    window = window.intersection(full_window)

    # Read only our selected cells.
    data = src.read(1, window=window, masked=True)

    if data.size == 0:
        raise ValueError("No raster cells found for DC.")

    new_transform = src.window_transform(window)

    # Convert masked values into explicit NaN values.
    clean_data = np.asarray(
        data.astype("float32").filled(np.nan)
    )

    metadata = src.profile.copy()

    metadata.update(
        driver="GTiff",
        height=clean_data.shape[0],
        width=clean_data.shape[1],
        count=1,
        dtype="float32",
        transform=new_transform,
        nodata=np.nan,
        compress="deflate"
    )

    # Save the smaller, geographic raster.
    with rasterio.open(
        output_raster, "w", **metadata
    ) as dst:
        dst.write(clean_data, 1)


# SECTION 7: Record metadata and missingness

valid_cells = np.isfinite(clean_data)
total_cells = clean_data.size
usable_cells = int(valid_cells.sum())

source_metadata = {
    "source": "PRISM Climate Group",
    "variable": "daily precipitation",
    "variable_code": "ppt",
    "units": "mm",
    "event_id": "FLOOD_125",
    "observation_date": str(event_date.date()),
    "temporal_resolution": "daily",
    "temporal_interval_convention":
        "Verify against PRISM documentation",
    "requested_resolution": resolution,
    "native_crs": str(metadata["crs"]),
    "native_pixel_size": list(src_resolution)
        if False else None,
    "study_bbox_lonlat": [west, south, east, north],
    "download_url": url,
    "retrieved_at_utc": datetime.now(
        timezone.utc
    ).isoformat(),
    "total_cells": total_cells,
    "usable_cells": usable_cells,
    "missing_cells": total_cells - usable_cells,
    "missing_fraction": (
        (total_cells - usable_cells) / total_cells
    ),
    "output_file": output_raster.name
}

# Retrieve the stored raster's actual resolution.
with rasterio.open(output_raster) as check:
    source_metadata["native_pixel_size"] = list(
        check.res
    )

metadata_path = raster_dir / (
    f"prism_ppt_{resolution}_{date_string}_metadata.json"
)

with open(metadata_path, "w") as f:
    json.dump(source_metadata, f, indent=4)


# SECTION 8: Print results

print("\nProcessed raster saved to:")
print(output_raster)

print("\nMetadata saved to:")
print(metadata_path)

print("\nPrecipitation summary:")
print("Number of grid cells:", total_cells)
print("Usable grid cells:", usable_cells)
print("Missing grid cells:", total_cells - usable_cells)

if usable_cells > 0:
    print(
        "Minimum rainfall (mm):",
        float(np.nanmin(clean_data))
    )
    print(
        "Maximum rainfall (mm):",
        float(np.nanmax(clean_data))
    )
    print(
        "Mean rainfall (mm):",
        float(np.nanmean(clean_data))
    )
else:
    print("No usable precipitation cells were found.")

print("\nStep 3 download and processing complete!")
