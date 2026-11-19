# Houston Hurricane Impact Forecasting

CSE 472 Project 2: forecast Houston 311 service demand during hurricane events.

## Project layout

- `config/event_category_rules.csv` records the current category decisions.
- `data/raw/` holds local copies of source data; keep the originals in Google Drive.
- `data/interim/` is for intermediate data products.
- `data/processed/geography/houston_grid.gpkg` is the provided Houston 1 km grid. Its existing cell IDs are preserved.
- `docs/` contains project decisions and QA notes.
- `outputs/` contains generated audit and model results.
- `scripts/` contains grid preparation, reusable 311 filters, and weather/Census validation scripts.

`data/` and `outputs/` are ignored by Git. Expected local source filenames and paths:

| Source | Local relative path | Source handling |
|---|---|---|
| Houston 2017 annual 311 extract | `data/raw/311-CRIS-Public-Data-Extract-D365-YTD-compressed-2017.txt` | Keep the original in Google Drive; a local working copy is in this path. |
| Houston 2021 annual 311 extract | `data/raw/311-CRIS-Public-Data-Extract-D365-YTD-compressed-2021.txt` | Keep the original in Google Drive; a local working copy is in this path. |
| Houston full-purpose boundary source | `data/raw/houston_full_purpose_source.geojson` | Keep the original in Google Drive; obtain a local copy here if rebuilding the grid. |
| Houston grid | `data/processed/geography/houston_grid.gpkg` | Provided grid copied into the project; use its existing cell IDs. |

## Harvey category decisions

Flooding, Storm Debris Collection, Crisis Cleanup, Street Hazard, Tree Removal, Street Condition, Traffic Signal Maintenance, Traffic Signals, and Water Leak are automatic includes within each selected storm window. Automatic categories qualify even with blank descriptions. Other categories may qualify through configured description rules. See [the Harvey audit notes](docs/harvey_audit.md), [the category rules](config/event_category_rules.csv), and the event-specific phrase configs.

## Harvey audit

From the project root, run:

```sh
.venv/bin/python scripts/audit_harvey_311.py \
  data/raw/311-CRIS-Public-Data-Extract-D365-YTD-compressed-2017.txt \
  data/processed/geography/houston_grid.gpkg \
  outputs/harvey \
  2017-08-25 2017-09-08
```

The end date is exclusive, so this selects Aug 25 through Sep 7, 2017 UTC. The project-local Conda environment at `.venv/` includes GDAL bindings (`osgeo`). The audit completed with 17,340 grid assignments. Details are in [the audit notes](docs/harvey_audit.md).

## Filtered Harvey grid counts

Run the approved-category and description-phrase filter from the project root:

```sh
.venv/bin/python scripts/filter_harvey_311.py \
  data/raw/311-CRIS-Public-Data-Extract-D365-YTD-compressed-2017.txt \
  data/processed/geography/houston_grid.gpkg \
  config/event_category_rules.csv \
  config/harvey_filter.json \
  data/processed/harvey_311_grid_counts.csv \
  outputs/qa/harvey/reconciliation.json \
  outputs/qa/harvey/daily_keyword_comparison.csv \
  outputs/qa/harvey/keyword_match_audit.csv \
  2017-08-25 2017-09-08
```

The processed CSV includes all grid cells and separates the automatic-category baseline from description-keyword additions. The reconciliation JSON reports category and rule counts and spatial outcomes. The daily file has 28 prior-window days and 14 event-window days; the audit CSV preserves request IDs and matched rule IDs for event candidates. The six added shared categories are automatic for both storms.

## Nicholas 311 grid counts

The Nicholas window and storm phrases are recorded in `config/nicholas_event.json` and `config/nicholas_filter.json`. Run the reused filter with the UTC window from Sep 11 through Sep 24, 2021:

```sh
.venv/bin/python scripts/filter_harvey_311.py \
  data/raw/311-CRIS-Public-Data-Extract-D365-YTD-compressed-2021.txt \
  data/processed/geography/houston_grid.gpkg \
  config/event_category_rules.csv \
  config/nicholas_filter.json \
  data/processed/nicholas/311_grid_counts.csv \
  outputs/qa/nicholas/reconciliation.json \
  outputs/qa/nicholas/daily_keyword_comparison.csv \
  outputs/qa/nicholas/keyword_match_audit.csv \
  2021-09-11 2021-09-25
```

For Nicholas, the event filter also automatically includes Disaster Recovery Escalation, Severe Storm Tree Removal, and Spilled Debris; these additions do not change Harvey’s configuration. The [Nicholas audit notes](docs/nicholas_311.md) summarize schema, track-window selection, category mapping, and the verified outputs. Category decisions are in `config/nicholas_category_mapping.csv`.

## Weather and Census inputs

Large inputs are kept in Git-ignored paths. HURDAT2 and storm tracks are under `data/raw/weather/tracks/`; Stage IV files are under `data/raw/weather/stage_iv_conus/` with their inventory at `data/raw/weather/stage_iv_inventory.csv`; the TIGER GeoPackage is at `data/raw/census/houston_tiger_block_groups.gpkg`. The supplied track-distance CSV is preserved at `data/raw/weather/track_distance_by_cell.csv`.

Reproduce distances from the HURDAT2 archive and verify the track and 311 joins with:

```sh
.venv/bin/python scripts/derive_track_distance.py \
  data/processed/geography/houston_grid.gpkg
.venv/bin/python scripts/join_track_distance.py
```

Generated distances are saved to `data/processed/weather/track_distance_by_cell.csv`; joined 311 tables are saved separately under `data/processed/harvey/` and `data/processed/nicholas/`. The [weather/Census input notes](docs/weather_census_inputs.md) document package paths, validation results, and outstanding rainfall, ACS, and wind work. The join verification report is `outputs/qa/weather_census/reconciliation.json`.
