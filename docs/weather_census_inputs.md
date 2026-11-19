# Houston weather and Census inputs

Collected and checked on November 19, 2026. Use the existing Houston grid with 2,127 cells. The track table is keyed by storm ID and cell ID.

| Storm | NHC ID | Working weather window, midnight UTC to exclusive end | Stage IV archive dates collected |
|---|---|---|---|
| Harvey | AL092017 | Aug 25 to Sep 1, 2017 | Aug 25 to Sep 1 |
| Nicholas | AL142021 | Sep 11 to Sep 18, 2021 | Sep 11 to Sep 18 |
| Beryl | AL022024 | Jul 5 to Jul 12, 2024 | Jul 5 to Jul 12 |

## Weather

- **Tracks.** The package contains the full [NHC HURDAT2 release dated September 23, 2026](https://prod-east-nhc.woc.noaa.gov/data/hurdat/hurdat2-1851-2025-092326.txt) and CSV extracts for Harvey (74 fixes), Nicholas (21), and Beryl (57). Each extract preserves quadrant wind radii and the radius of maximum wind in nautical miles. Missing values are blank. Harvey has radius-of-maximum-wind values at two fixes near its initial Texas landfall. Nicholas and Beryl have values at all fixes in this release.
- **Track distance.** The table contains 6,381 rows. Distances are computed from an interior representative point for each clipped cell to the storm-center path in the grid's NAD83 / UTM 15N coordinates. The script uses linear interpolation to clip segments to the working event windows, only where best-track fixes bracket the segment. Run the script with the existing GeoPackage and Python with GDAL bindings.
- **Observed rain.** The package contains 24 unmodified CONUS 24-hour Stage IV files extracted from [NOAA's daily archives](https://water.noaa.gov/about/precipitation-data-access), eight per event. The inventory records each file's original archive URL, SHA-256 and timestamps from its GRIB metadata. The files accumulate from noon UTC to noon UTC and bracket the working midnight windows. To compute exact midnight-window totals, use compatible subdaily Stage IV data for the two edge half-days. The six complete interior daily fields can be used directly. Preserve the native grid and missing-data flags when calculating cell totals.
- **Modeled wind.** The extracted tracks supply track and intensity inputs. Hourly local winds, peak gust and cumulative wind exposure still need to be modeled. A consistent radius-of-maximum-wind treatment for periods with missing data remains necessary.

## Census

The GeoPackage includes the full 2015, 2019 and 2022 TIGER block groups that intersect the Houston footprint. The layers contain 1,567 (2015), 1,566 (2019), and 1,904 (2022) block groups, spanning Brazoria, Fort Bend, Harris, and Montgomery counties. Each layer covers the full Houston footprint by area. Polygons retain their area outside Houston for later population and housing allocation. The corresponding ACS estimates still need retrieval and a GEOID join. The Census API responded with “Missing Key” for the attempted requests. The [Census summary files](https://www.census.gov/programs-surveys/acs/data/summary-file.html) provide another route.

Source archives are [2015 Texas TIGER block groups](https://www2.census.gov/geo/tiger/TIGER2015/BG/tl_2015_48_bg.zip), [2019 Texas TIGER block groups](https://www2.census.gov/geo/tiger/TIGER2019/BG/tl_2019_48_bg.zip), and [2022 Texas TIGER block groups](https://www2.census.gov/geo/tiger/TIGER2022/BG/tl_2022_48_bg.zip). The subsetting script takes the existing Houston grid and those three ZIP files.

## Teammate files

- [Block-group boundaries](https://drive.google.com/file/d/1Tf68VAx5f4waHcbUHAW45I67Sp600t6v/view), [environment and rain](https://drive.google.com/file/d/1OtSknqn2nKg9xH38OW8g7dOjv0x7vyuv/view), [scope](https://drive.google.com/file/d/1vyCvoDlbr6NEnFT9ucZxSN2ADGjBkPnO/view), and [existing Census table](https://drive.google.com/file/d/1Ocs_GtRnlsK95BhGSga50D-Hj9_Tj9xW/view) share exactly the same 2,144 Harris County block-group IDs. The polygons cover 97.6% of the current Houston footprint by area. The environment table has complete Harvey rain and elevation values at block-group resolution. Use it to cross-check the new gridded features after confirming its aggregation and event window. The scope table covers an earlier block-group analysis and includes baseline counts.
- NFIP policies are a candidate insurance input if that feature is adopted. The NSI inventory is low priority because building count was dropped. Neither file is required for the initial weather predictors.

## Repository paths and reproduction

The package was extracted into the repository's Git-ignored data directories. The ZIP remains at `/Users/eliasricken/Downloads/Houston_Weather_and_Census_Inputs.zip`.

| Input or output | Repository path |
|---|---|
| NHC HURDAT2 archive | `data/raw/weather/tracks/hurdat2-1851-2025-092326.txt` |
| Supplied Harvey, Nicholas, and Beryl track CSVs | `data/raw/weather/tracks/{harvey,nicholas,beryl}_best_track.csv` |
| Stage IV GRIB/GRIB2 files | `data/raw/weather/stage_iv_conus/{Harvey,Nicholas,Beryl}/` |
| Stage IV source, SHA-256, and time inventory | `data/raw/weather/stage_iv_inventory.csv` |
| Package-provided track distance table | `data/raw/weather/track_distance_by_cell.csv` |
| TIGER block-group GeoPackage | `data/raw/census/houston_tiger_block_groups.gpkg` |
| Reproduced track distance table | `data/processed/weather/track_distance_by_cell.csv` |
| Re-extracted track CSVs | `data/processed/weather/tracks/` |
| Harvey 311 plus track distance | `data/processed/harvey/311_grid_with_track_distance.csv` |
| Nicholas 311 plus track distance | `data/processed/nicholas/311_grid_with_track_distance.csv` |
| Validation report | `outputs/qa/weather_census/reconciliation.json` |

From the project root, recreate the distance table from HURDAT2 and the fixed grid, then validate the package table and join distances to both available 311 grids:

```sh
.venv/bin/python scripts/derive_track_distance.py \
  data/processed/geography/houston_grid.gpkg
.venv/bin/python scripts/join_track_distance.py
```

The derivation uses each storm's package-defined anchor date, clips the track to the working weather window, interpolates only between bracketing fixes, and measures from each grid cell's interior representative point in EPSG:26915. `join_track_distance.py` checks each `(storm_id, cell_id)` key against the fixed grid, compares the reproduced table with the supplied table, writes the two 311 joins, and confirms that the 311 cell totals do not change.

## Outstanding data and modeling work

- The supplied Stage IV files are 24-hour accumulations from noon UTC to noon UTC. Exact totals for the midnight-to-midnight working windows require compatible subdaily data for the edge intervals; those inputs are not in this package. The Stage IV inventory currently has 24 entries, eight per storm, and all listed file hashes have been verified.
- The TIGER block-group polygons are present, but matching ACS estimates and the GEOID join are not. TIGER's source ZIP archives are also not included; the supplied GeoPackage is ready to use, and the source URLs above support rebuilding it if needed.
- Wind predictors have not been modeled. Hourly local wind, peak gust, and cumulative exposure remain to be derived from the track and intensity inputs.

## Verification results

The supplied and reproduced track-distance tables each contain 6,381 rows: exactly 2,127 per storm, with unique composite keys and exactly the fixed grid's cell IDs for Harvey (`AL092017`), Nicholas (`AL142021`), and Beryl (`AL022024`). The regenerated distances match the supplied table exactly at the stored six-decimal precision.

The Harvey and Nicholas 311 joins each contain 2,127 rows, with zero unmatched 311 or track cell IDs. Their 311 category-only, keyword-added, and combined totals are unchanged by the join. The validation JSON records the component totals and checks. No Beryl 311 cell table was available to join.
