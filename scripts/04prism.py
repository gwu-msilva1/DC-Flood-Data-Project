
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


# SECTION 1: Project settings

ROOT = Path(__file__).resolve().parent.parent

EVENTS_FILE = ROOT / "data/processed/flood_events_cleaned.csv"
RASTER_DIR = ROOT / "data/processed/rasters"
OUTPUT_DIR = ROOT / "outputs"

RASTER_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

RESOLUTION = "800m"
MAX_DATES = None
BUFFER_DAYS = 1
MAX_ATTEMPTS = 3

# Study area: DC and surrounding region
WEST, SOUTH, EAST, NORTH = -77.20, 38.78, -76.85, 39.02

REPORT_FILE = OUTPUT_DIR / f"prism_availability_{RESOLUTION}.csv"
INVENTORY_FILE = OUTPUT_DIR / "prism_requested_dates.csv"
EVENT_REPORT = OUTPUT_DIR / f"prism_event_coverage_{RESOLUTION}.csv"


# SECTION 2: Load flood events

events = pd.read_csv(EVENTS_FILE, dtype={"event_id": str})

if events["event_id"].isna().any():
    raise ValueError("Missing event IDs.")

if events["event_id"].duplicated().any():
    raise ValueError("Duplicate event IDs.")

events["begin_date"] = pd.to_datetime(events["begin_date"])
events["end_date"] = pd.to_datetime(events["end_date"])

if (events["end_date"] < events["begin_date"]).any():
    raise ValueError("An event ends before it begins.")

print("Number of flood events:", len(events))


# SECTION 3: Build the requested-date inventory

date_to_events = {}
event_to_dates = {}

for row in events.itertuples(index=False):

    start = row.begin_date - pd.Timedelta(days=BUFFER_DAYS)
    end = row.end_date + pd.Timedelta(days=BUFFER_DAYS)

    dates = [
        d.strftime("%Y%m%d")
        for d in pd.date_range(start, end)
    ]

    event_to_dates[row.event_id] = dates

    for date in dates:
        date_to_events.setdefault(date, set()).add(row.event_id)

all_dates = sorted(date_to_events)

print("Unique requested dates:", len(all_dates))

pd.DataFrame([
    {
        "date": date,
        "event_ids": ";".join(sorted(date_to_events[date]))
    }
    for date in all_dates
]).to_csv(INVENTORY_FILE, index=False)

selected_dates = (
    all_dates if MAX_DATES is None
    else all_dates[:MAX_DATES]
)

print("Dates selected for this run:", len(selected_dates))


# SECTION 4: File names

def paths_for(date):
    raster = (
        RASTER_DIR /
        f"prism_ppt_{RESOLUTION}_{date}_dc.tif"
    )
    metadata = (
        RASTER_DIR /
        f"prism_ppt_{RESOLUTION}_{date}_metadata.json"
    )
    return raster, metadata


# SECTION 5: Validate saved files

def check_existing(date):

    raster_path, metadata_path = paths_for(date)

    if not raster_path.exists() or not metadata_path.exists():
        return None

    try:
        with open(metadata_path, encoding="utf-8") as f:
            metadata = json.load(f)

        if metadata.get("date") != date:
            return None

        if metadata.get("resolution_product") != RESOLUTION:
            return None

        with rasterio.open(raster_path) as src:

            if src.count != 1 or src.crs is None:
                return None

            if src.width == 0 or src.height == 0:
                return None

            data = src.read(1, masked=True)
            valid = int(np.ma.count(data))
            total = int(data.size)

            if valid == 0:
                return None

            if metadata.get("total_cells") != total:
                return None

            if metadata.get("valid_cells") != valid:
                return None

            if metadata.get("crs") != str(src.crs):
                return None

        return {
            "total_cells": total,
            "valid_cells": valid,
            "missing_cells": total - valid,
            "file_bytes": raster_path.stat().st_size
        }

    except (OSError, ValueError, KeyError, TypeError,
            json.JSONDecodeError, rasterio.errors.RasterioError):
        return None


# SECTION 6: Download with retry handling

def download_prism(date, destination):

    url = (
        "https://services.nacse.org/prism/data/get/"
        f"us/{RESOLUTION}/ppt/{date}"
    )

    for attempt in range(1, MAX_ATTEMPTS + 1):

        try:
            with requests.get(
                url, stream=True, timeout=(30, 180)
            ) as response:

                response.raise_for_status()

                with open(destination, "wb") as f:
                    for chunk in response.iter_content(1024 * 1024):
                        if chunk:
                            f.write(chunk)

            if not is_zipfile(destination):
                raise ValueError("Response is not a valid ZIP.")

            return url

        except requests.HTTPError as exc:
            status = exc.response.status_code

            # Retry only temporary HTTP failures.
            if status not in (429, 500, 502, 503, 504):
                raise

            if attempt == MAX_ATTEMPTS:
                raise

        except (requests.Timeout, requests.ConnectionError):
            if attempt == MAX_ATTEMPTS:
                raise

        print(f"Temporary error. Retry {attempt}/{MAX_ATTEMPTS}")
        time.sleep(2 ** attempt)


# SECTION 7: Download and process a single date

def process_date(date):

    existing = check_existing(date)

    if existing is not None:
        return "reused", existing

    raster_path, metadata_path = paths_for(date)

    with TemporaryDirectory() as temp_name:

        temp_dir = Path(temp_name)
        zip_path = temp_dir / "download.zip"
        source_path = temp_dir / "source.tif"

        url = download_prism(date, zip_path)

        with ZipFile(zip_path) as archive:

            tif_files = [
                name for name in archive.namelist()
                if name.lower().endswith(".tif")
                and not name.startswith("__MACOSX/")
            ]

            if len(tif_files) != 1:
                raise ValueError(
                    f"Expected one GeoTIFF, found {len(tif_files)}"
                )

            with archive.open(tif_files[0]) as src_file:
                with open(source_path, "wb") as target:
                    shutil.copyfileobj(src_file, target)

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

            data = src.read(1, window=window, masked=True)

            if data.size == 0:
                raise ValueError("No grid cells in study area.")

            clean = data.astype("float32").filled(np.nan)

            total = int(clean.size)
            valid = int(np.isfinite(clean).sum())

            if valid == 0:
                raise ValueError("Raster has no usable cells.")

            profile = src.profile.copy()
            source_crs = str(src.crs)
            source_resolution = list(src.res)
            source_nodata = src.nodata

            profile.update(
                driver="GTiff",
                count=1,
                height=clean.shape[0],
                width=clean.shape[1],
                dtype="float32",
                transform=src.window_transform(window),
                nodata=np.nan,
                compress="deflate"
            )

        # Write a temporary output before replacing the final file.
        temporary_raster = temp_dir / "cropped.tif"

        with rasterio.open(temporary_raster, "w", **profile) as dst:
            dst.write(clean, 1)

        shutil.copy2(temporary_raster, raster_path)

        metadata = {
            "source": "PRISM Climate Group",
            "variable": "ppt",
            "units": "mm",
            "date": date,
            "resolution_product": RESOLUTION,
            "crs": source_crs,
            "native_resolution": source_resolution,
            "source_nodata": source_nodata,
            "temporal_resolution": "daily",
            "day_boundary": "Not independently verified",
            "study_bbox_lonlat": [WEST, SOUTH, EAST, NORTH],
            "download_url": url,
            "retrieved_at_utc": datetime.now(
                timezone.utc
            ).isoformat(),
            "event_ids": sorted(date_to_events[date]),
            "total_cells": total,
            "valid_cells": valid,
            "missing_cells": total - valid,
            "output_file": raster_path.name
        }

        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4)

    checked = check_existing(date)

    if checked is None:
        raise ValueError("Saved raster failed validation.")

    return "downloaded", checked


# SECTION 8: Load previous availability results

if REPORT_FILE.exists():
    old_report = pd.read_csv(
        REPORT_FILE, dtype={"date": str}
    ).set_index("date").to_dict("index")
else:
    old_report = {}

results = {}

for date in all_dates:

    previous = old_report.get(date, {})
    checked = check_existing(date)

    if checked is not None:
        status = "available"
        details = checked
        error = ""
    else:
        status = (
            "failed" if previous.get("status") == "failed"
            else "not_attempted"
        )
        details = {}
        error = previous.get("error", "") if status == "failed" else ""

    results[date] = {
        "date": date,
        "status": status,
        "last_action": previous.get("last_action", ""),
        "error": error,
        "event_ids": ";".join(sorted(date_to_events[date])),
        "resolution": RESOLUTION,
        "total_cells": details.get("total_cells"),
        "valid_cells": details.get("valid_cells"),
        "missing_cells": details.get("missing_cells"),
        "file_bytes": details.get("file_bytes")
    }


# SECTION 9: Save the availability report

def save_report():
    pd.DataFrame(
        [results[d] for d in all_dates]
    ).to_csv(REPORT_FILE, index=False)


save_report()


# SECTION 10: Process the selected dates

for i, date in enumerate(selected_dates, start=1):

    print(f"\nProcessing {i}/{len(selected_dates)}: {date}")

    try:
        action, details = process_date(date)

        results[date].update({
            "status": "available",
            "last_action": action,
            "error": "",
            **details
        })

        print("Result:", action)

    except Exception as exc:

        results[date]["status"] = "failed"
        results[date]["last_action"] = "failed"
        results[date]["error"] = str(exc)

        print("Failed:", exc)

    save_report()


# SECTION 11: Summarize coverage by event

coverage_rows = []

for event_id, dates in event_to_dates.items():

    available = sum(
        results[d]["status"] == "available"
        for d in dates
    )

    failed = sum(
        results[d]["status"] == "failed"
        for d in dates
    )

    requested = len(dates)

    coverage_rows.append({
        "event_id": event_id,
        "requested_dates": requested,
        "available_dates": available,
        "failed_dates": failed,
        "not_attempted_dates": requested - available - failed,
        "coverage_fraction": available / requested
    })

pd.DataFrame(coverage_rows).to_csv(
    EVENT_REPORT, index=False
)


# SECTION 12: Print the final results

report = pd.DataFrame([results[d] for d in all_dates])

print("\nBatch processing complete!")

print("\nAvailability across all requested dates:")
print(report["status"].value_counts())

print("\nTotal dates requested:", len(all_dates))
print("Dates processed in this run:", len(selected_dates))

print("\nAvailability report:", REPORT_FILE)
print("Event coverage report:", EVENT_REPORT)
print("Date inventory:", INVENTORY_FILE)
