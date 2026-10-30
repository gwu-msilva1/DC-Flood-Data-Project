DC Flood Data Project


Overview:
This project for STAT 6289 develops a reproducible virtual environmental database for flood events in Washington, DC using precipitation measurements from the PRISM Climate Group and water level observations from the U.S. Geological Survey. The data is processed and organized into an HDF5 database using Python. 


Data Sources:
Flood event records: provided csv: DC_flood_times.csv 
Precipitation observations: PRISM Climate Group
    Includes 372 daily precipitation rasters containing daily precipitation values in millimeters for the area 38.779°–39.021° N and 77.204°–76.854° W.
Water level observations: U.S. Geological Survey Water Data
    Four stations were used: Rock Creek at Sherrill Drive, Rock Creek at Joyce Road, Anacostia River near Buzzard Point, Anacostia River at Kenilworth. There are 192 available station event datasets and 59990 gauge height observations.
Independent precipitation investigation: NOAA National Centers for Environmental Information
    There are 10473 daily records from January 1, 1996 - December 31, 2025 which have 10283 numerical precipitation values, 190 missing precipitation values, and 124 of 125 had a numerical precipitation measurement on the same calendar date as the event start.


Data Collection and Processing:
Flood event CSV: each event assigned an identifier and stored with its reported start and end times, UTC timestamps, and duration.
PRISM: retrieved daily precipitation raster data, extracted downloaded raster files, selected region, converted data into grid, preserved values and spatial data, and recorded data availability and missing values for the specified dates.
USGS: identified time frames and event coverage, requested observations from USGS data service, used a time window of 24 hours before and after each event, preserved UTC timestamp and other measurements, recorded unsuccessful data, and evaluated missing data for the station and flood events.
For spatial and temporal data see outputs/spatial_temporal_report.md.


HDF5 Database:
The processed data is stored in data/hdf5/dc_flood_data.h5 with the following structure:

    events/
        event_ids
        FLOOD_XXX/
            record_json

    precipitation/
        YYYYMMDD/
            values
            valid_mask
            metadata_json

    gauges
        station_id/
            FLOOD_XXX/
                time_utc
                gauge_height
                unit
                approval_status
                metadata_json

    metadata
        supporting source and quality reports


Data Quality and Validation:
All PRISM precipitation dates were successfully collected with a final availability assessment reporting 100% coverage and no missing cells. Out of the 500 possible USGS observations, 192 had available data while the rest were outside the relevant time frames. An assessment of the collected measurements showed 59990 valid observations, 12 datasets with internal time gaps, and 77 missing readings. The missing observations were documented. An integrity validation test performed 4101 checks all of which were passed and a reusability validation test performed 9 tests all of which were passed.


Reproducibility:
Software: 
Python, Visual Studio Code, Git, and GitHub used and Python dependencies are in requirements.txt.
Create a virtual environment > python -m venv .venv
Activate the environment in terminal > .\.venv\Scripts\Activate.ps1
Install the dependencies > python -m pip install -r requirements.txt

HDF5 Database:
The HDF5 database can be used to retrieve stored events, precipitation rasters, and gauge measurements without downloading the original data.
Verify the database > python scripts/13hdf5verify.py
Test reusability > python scripts/19testhdf5.py
Test extended retrieval functions > python scripts/23testhdf5extended.py
Verify source-to-HDF5 integrity when the processed source files are available > python scripts/14hdf5integrity.py

Building Database and Visualizations:
The project includes scripts for cleaning data, downloading PRISM precipitation, collecting USGS measurements, assessment, and building the HDF5 database. The main building script is python scripts/12hdf5build.py. The project includes scripts that generate figures directly from the HDF5 database. The generated figures are in outputs/figures/.
Create a PRISM precipitation map > python scripts/16hdf5percipitationmap.py
Create a USGS gauge-height graph > python scripts/17hdf5gaugeplot.py
Create a combined precipitation and gauge-height visualization > python scripts/18combinedhdf5.py

Functions:
The project provides Python functions for listing events and USGS stations, listing dates and identifying sources, retrieving rasters by date or event, retrieving gauge observations for specific events, and summarizing precipitation and gauge availability.


Limitations:
The limitations of this project include different measuring methods between PRISM and USGS, PRISM accumulation boundary not independently verified, PRISM precipitation dates do not exactly align with event time frames, missing USGS values, and unverified data from the Rock Creek stations.


Sources:
PRISM Climate Group: https://prism.oregonstate.edu/
USGS Water Data: https://waterdata.usgs.gov/
USGS Water Data APIs: https://api.waterdata.usgs.gov/
NOAA NCEI Daily Summaries: https://www.ncei.noaa.gov/access/services/data/v1
NOAA GHCN-Daily Documentation: https://www.ncei.noaa.gov/pub/data/cdo/documentation/GHCND_documentation.pdf
HDF5 Documentation: https://www.hdfgroup.org/solutions/hdf5/


AI Use Acknowledgment:
ChatGPT was used to assist with programming, debugging, and documentation. 