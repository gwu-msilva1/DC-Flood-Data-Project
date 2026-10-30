
from pathlib import Path
import json

import h5py
import pandas as pd


# SECTION 1: Locate the project

ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT / "data"
SCRIPTS_DIR = ROOT / "scripts"
OUTPUT_DIR = ROOT / "outputs"

HDF5_FILE = DATA_DIR / "hdf5/dc_flood_data.h5"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# SECTION 2: Define important project files

required_files = {
    "Cleaned flood events":
        DATA_DIR / "processed/flood_events_cleaned.csv",

    "USGS station inventory":
        DATA_DIR / "metadata/usgs_gauge_inventory.csv",

    "HDF5 database":
        HDF5_FILE,

    "HDF5 integrity report":
        OUTPUT_DIR / "hdf5_integrity_report.csv",

    "HDF5 reusability report":
        OUTPUT_DIR / "hdf5_reusability_tests.csv",

    "README":
        ROOT / "README.md",

    "Requirements":
        ROOT / "requirements.txt",

    "Git ignore":
        ROOT / ".gitignore"
}


# SECTION 3: Check file existence

print("=== REQUIRED PROJECT FILES ===")

file_checks = {}

for label, path in required_files.items():

    exists = path.is_file()

    file_checks[label] = exists

    status = "FOUND" if exists else "MISSING"

    print(f"{status}: {label}")


# SECTION 4: Count project data

print("\n=== DATA INVENTORY ===")

prism_files = list(
    (DATA_DIR / "processed/rasters").glob(
        "prism_ppt_800m_*_dc.tif"
    )
)

gauge_files = list(
    (DATA_DIR / "processed/gauges").glob(
        "gauge_USGS-*_FLOOD_*.csv"
    )
)

gauge_metadata = list(
    (DATA_DIR / "processed/gauges").glob(
        "gauge_USGS-*_FLOOD_*_metadata.json"
    )
)

python_files = list(
    SCRIPTS_DIR.glob("*.py")
)

figure_files = list(
    (OUTPUT_DIR / "figures").glob("*.png")
)

counts = {
    "prism_rasters": len(prism_files),
    "gauge_csv_files": len(gauge_files),
    "gauge_metadata_files": len(gauge_metadata),
    "python_scripts": len(python_files),
    "png_figures": len(figure_files)
}

for name, value in counts.items():
    print(f"{name}: {value}")


# SECTION 5: Inspect the HDF5 database

database_info = {}

if HDF5_FILE.exists():

    with h5py.File(HDF5_FILE, "r") as h5:

        database_info = {
            "events": int(h5.attrs["event_count"]),
            "rasters": int(h5.attrs["raster_count"]),
            "gauge_datasets": int(
                h5.attrs["gauge_dataset_count"]
            ),
            "gauge_observations": int(
                h5.attrs["gauge_observation_count"]
            ),
            "file_size_mb": round(
                HDF5_FILE.stat().st_size / 1e6, 2
            )
        }

    print("\n=== HDF5 DATABASE ===")

    for name, value in database_info.items():
        print(f"{name}: {value}")


# SECTION 6: Check integrity and reusability reports

test_results = {}

report_paths = {
    "integrity":
        OUTPUT_DIR / "hdf5_integrity_report.csv",
    "reusability":
        OUTPUT_DIR / "hdf5_reusability_tests.csv"
}

for name, path in report_paths.items():

    if path.exists():
        report = pd.read_csv(path)

        test_results[name] = {
            "checks": int(len(report)),
            "passed": int(report["passed"].sum()),
            "failed": int((~report["passed"]).sum())
        }

print("\n=== VALIDATION REPORTS ===")

for name, values in test_results.items():
    print(name, values)


# SECTION 7: Save final audit

summary = {
    "required_files": file_checks,
    "data_counts": counts,
    "database": database_info,
    "validation": test_results
}

audit_file = OUTPUT_DIR / "project_audit.json"

with open(audit_file, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=4)


# SECTION 8: Print final summary

print("\n=== FINAL PROJECT AUDIT ===")

missing = [
    name for name, exists in file_checks.items()
    if not exists
]

if missing:
    print("Required files needing attention:")
    for name in missing:
        print("-", name)
else:
    print("All listed required files are present.")

print("\nAudit saved to:")
print(audit_file)

print("\nProject inventory complete!")
