
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from hdf5_functions import get_precipitation


# SECTION 1: Choose a date

DATE = "2025-07-19"


# SECTION 2: Retrieve precipitation from HDF5

rainfall, mask, metadata = get_precipitation(DATE)

print("Selected date:", DATE)
print("Raster shape:", rainfall.shape)
print("Coordinate system:", metadata["crs"])

# Exclude invalid cells from the map.
rainfall = np.where(mask, rainfall, np.nan)


# SECTION 3: Locate geographic boundaries

left, bottom, right, top = metadata["bounds"]


# SECTION 4: Create the precipitation map

fig, ax = plt.subplots(figsize=(11, 7))

image = ax.imshow(
    rainfall,
    extent=[left, right, bottom, top],
    origin="upper",
    cmap="Blues",
    vmin=0,
    interpolation="nearest",
    aspect="equal"
)

colorbar = fig.colorbar(
    image,
    ax=ax,
    shrink=0.85
)

colorbar.set_label("Daily precipitation (mm)")

ax.set_title(
    "PRISM Daily Precipitation\n"
    f"Washington, DC Area — {DATE}"
)

ax.set_xlabel("Longitude (degrees)")
ax.set_ylabel("Latitude (degrees)")

ax.grid(alpha=0.15)

plt.tight_layout()


# SECTION 5: Save the map

ROOT = Path(__file__).resolve().parent.parent

FIGURE_DIR = ROOT / "outputs" / "figures"
FIGURE_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = (
    FIGURE_DIR /
    f"hdf5_prism_precipitation_{DATE}.png"
)

plt.savefig(
    OUTPUT_FILE,
    dpi=300,
    bbox_inches="tight"
)

print("Precipitation map saved to:", OUTPUT_FILE)

plt.show()

print("Precipitation map completed!")
