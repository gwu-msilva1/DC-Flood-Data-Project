Independent Investigation of Additional Precipitation Observations inside Washington, DC

Data Source:
Data is from NOAA's Daily Summaries spanning from January 1, 1996 - December 31, 2025. 
Station: 
Name: National Arboretum, Washington, DC
NOAA station ID: USC00186350
38.91329° N, −76.97009° W

Availability & Limitations:
The retrieval returned 10473 station date records, including 10283 numerical precipitation values, 190 missing numerical precipitation values, 6896 zero precipitation values, and 3387 positive precipitation values. The records were compared with the start dates of the 125 flood events using the EST (UTC−5) time zone. A numerical precipitation observation was available for 124 of 125 dates and no usable same date measurement was available for FLOOD_122, on January 28, 2024. 743 records were designated as trace precipitation and 98 as missing presumed zero. Reported observation times vary with 7307 at 8:00 AM, 2976 at 7:00 AM, and 190 that were not specified. Limitations of this investigation include missing values, singular location/station, and daily totals don't give insight on time of precipitation.

Conclusion:
Overall, the National Arboretum station data is useful as it provides a substantial precipitation record with strong date coverage. Differences such as location, time, and accumulation periods must be considered when directly comparing this data to the used PRISM or USGS measurements. This independent investigation is not incorporated into this project's HDF5 database.

Sources:
NOAA NCEI Daily Summaries: https://www.ncei.noaa.gov/access/services/data/v1
NOAA GHCN-Daily documentation: https://www.ncei.noaa.gov/pub/data/cdo/documentation/GHCND_documentation.pdf
NOAA station: USC00186350

Reproducibility:
Project scripts:
scripts/21dcprecipitation.py: data retrieval and flood-event date coverage
scripts/22dcquality.py: quality flags and surroundings analysis
Project outputs:
data/processed/dc_precipitation/noaa_arboretum_raw.csv
data/processed/dc_precipitation/noaa_arboretum_daily.csv
outputs/dc_precipitation/arboretum_event_date_coverage.csv
outputs/dc_precipitation/arboretum_summary.json