Spatial and Temporal Data Report
Spatial Data:
PRISM Precipitation:
This project stores 372 processed PRISM daily precipitation rasters in the DC area. The HDF5 audit verified that bounds, CRS, and geographic transforms are stored for all 372 precipitation rasters. An example test from July 19, 2025, contained 1218 valid grid cells and no missing cells

Property
Value
Source
PRISM Climate Group
Variable
Daily precipitation (mm)
Nominal resolution
800 m
Coordinate system
EPSG:4269 (NAD83)
Grid dimensions
29 × 42 cells
Pixel spacing
Approximately 0.008333°
Geographic extent
38.779°–39.021° N, 77.204°–76.854° W
NoData value
−9999

USGS Water-Level Stations:
This project includes four USGS water-level monitoring stations. Gauge height shouldn’t be interpreted as height above ground surface and the USGS gauge height is station specific so stations should not be directly compared.
Station
Latitude
Longitude
Rock Creek at Sherrill Drive
38.972500
−77.040000
Rock Creek at Joyce Road
38.960167
−77.042056
Anacostia River near Buzzard Point
38.865167
−77.010333
Anacostia River at Kenilworth
38.909167
−76.955278

Temporal Metadata:
Flood-event timestamps were converted from fixed EST to UTC to allow for direct  comparison with USGS observations. The USGS quality assessment found 12 station events with time gaps and 77 missing scheduled observations. PRISM precipitation represents daily accumulation totals but we can’t conclude that it establishes an exact temporal overlap because the accumulation day boundary is not independently verified.
Dataset
Temporal characteristics
Flood events
Fixed EST (UTC−5), including summer
PRISM precipitation
Daily totals
USGS gauge heights
UTC timestamps, typically sampled every 5 or 15 minutes
NOAA station precipitation
Daily totals with morning observation times

Conclusion and Limitations
The metadata audit inspected 3292 HDF5 objects, verifying the precipitation rasters properties, time zone conversions, and observation characteristics so we have the spatial and temporal information needed to interpret precipitation and water-level observations. Additionally, there are 4101 successful source to HDF5 integrity checks, 9 successful HDF5 reusability tests, and complete coordinates for all four stations in the corrected external inventory
Limitations of this include unverified Rock Creek gauge data, HDF5 station inventory, and uncertain daily precipitation accumulation periods. The NOAA National Arboretum investigation also demonstrated that station reporting times can differ from flood event intervals.
Project outputs:
data/metadata/usgs_gauge_inventory_corrected.csv
outputs/hdf5_metadata_audit.csv
outputs/hdf5_metadata_summary.json
outputs/usgs_gauge_quality.csv
outputs/prism_event_coverage_800m.csv
outputs/dc_precipitation/dc_precipitation_investigation.md
