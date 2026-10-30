
from pathlib import Path
import matplotlib.pyplot as plt
import rasterio
from rasterio.plot import plotting_extent

# Locate project folder
project_dir = Path(__file__).resolve().parent.parent

# Locate saved precipitation raster
raster_path = (
    project_dir / "data" / "processed" / "rasters"
    / "prism_ppt_4km_20250719_dc.tif"
)

# Locate output folder
figure_dir = project_dir / "outputs" / "figures"
figure_dir.mkdir(parents=True, exist_ok=True)

# Read the precipitation raster
with rasterio.open(raster_path) as src:
    rainfall = src.read(1, masked=True)
    extent = plotting_extent(src)
    crs = src.crs

# Create the precipitation map
fig, ax = plt.subplots(figsize=(10, 7))

image = ax.imshow(
    rainfall,
    extent=extent,
    origin="upper",
    cmap="Blues",
    interpolation="nearest"
)

# Add color legend
colorbar = fig.colorbar(image, ax=ax)
colorbar.set_label("Daily precipitation (mm)")

# Add title and geographic labels
ax.set_title(
    "PRISM Daily Precipitation — Washington, DC Area\n"
    "July 19, 2025",
    fontsize=14,
    pad=15
)

ax.set_xlabel("Longitude (degrees, NAD83)")
ax.set_ylabel("Latitude (degrees, NAD83)")

# Save the map
output_path = (
    figure_dir / "prism_precipitation_20250719.png"
)

fig.text(
    0.5, 0.01,
    "Source: PRISM Climate Group | "
    "Resolution: approximately 4 km | "
    "Daily precipitation (mm)",
    ha="center",
    fontsize=9
)

plt.tight_layout(rect=[0, 0.04, 1, 1])
plt.savefig(output_path, dpi=300)

plt.show()

print("Map saved to:", output_path)
print("Coordinate system:", crs)
print("Map created successfully!")
