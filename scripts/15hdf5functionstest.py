
# SECTION 1: Import our retrieval functions

from hdf5_functions import (
    get_flood_event,
    get_precipitation,
    get_gauge_data,
    list_precipitation_dates,
    list_gauge_events
)


# SECTION 2: Test flood-event retrieval

print("=== FLOOD EVENT TEST ===")

event = get_flood_event("FLOOD_125")

print("Event information:")

for key, value in event.items():
    print(f"{key}: {value}")


# SECTION 3: Test PRISM retrieval

print("\n=== PRISM TEST ===")

rainfall, mask, metadata = get_precipitation(
    "2025-07-19"
)

print("Date:", metadata["date"])
print("Raster shape:", rainfall.shape)
print("CRS:", metadata["crs"])
print("Bounds:", metadata["bounds"])
print("Valid cells:", mask.sum())

print(
    "Minimum rainfall (mm):",
    rainfall[mask].min()
)

print(
    "Maximum rainfall (mm):",
    rainfall[mask].max()
)


# SECTION 4: Test gauge retrieval

print("\n=== USGS GAUGE TEST ===")

gauge, gauge_metadata = get_gauge_data(
    "01648010", "FLOOD_125"
)

print("Station:", gauge_metadata["station_id"])
print("Event:", gauge_metadata["event_id"])
print("Observations:", len(gauge))

print("\nFirst five observations:")

print(
    gauge[
        ["time_utc", "gauge_height"]
    ].head().to_string(index=False)
)

print(
    "\nMinimum gauge height:",
    gauge["gauge_height"].min()
)

print(
    "Maximum gauge height:",
    gauge["gauge_height"].max()
)


# SECTION 5: Test the list functions

print("\n=== AVAILABLE DATA TEST ===")

dates = list_precipitation_dates()

print("PRISM dates available:", len(dates))

events = list_gauge_events("01648010")

print(
    "Joyce Road flood events available:",
    len(events)
)


print("\nAll HDF5 retrieval tests completed!")
