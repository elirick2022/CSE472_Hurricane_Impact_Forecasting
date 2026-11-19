# Harvey 311 audit

## Event category decisions

- **Flooding:** automatic include within the selected event window.
- **Storm Debris Collection:** automatic include within the selected event window.
- **Crisis Cleanup:** approved automatic include within the selected event window.
- **Street Hazard, Tree Removal, Street Condition, Traffic Signal Maintenance, Traffic Signals, and Water Leak:** automatic includes for all storms within the selected event window.

The automatic categories are read from `config/event_category_rules.csv` when the filtered step runs. `config/harvey_filter.json` supplies the description phrases for other categories. The all-category audit remains provisional spatial QA; filtered counts are a separate result.

## Window and expected QA

The selected window is **2017-08-25 00:00 UTC inclusive through 2017-09-08 00:00 UTC exclusive** (Aug 25 through Sep 7). The audit was run from the project-local Conda environment against the local annual extract and grid. It parsed 381,559 annual requests and found 17,690 requests in the window: 17,340 assigned to the grid, 173 with invalid coordinates, and 177 outside the grid. This matches the supplied QA results.

## Local inputs

- Grid: `data/processed/geography/houston_grid.gpkg` (provided GeoPackage copied unchanged; existing `cell_id` values are retained).
- Annual extract: `data/raw/311-CRIS-Public-Data-Extract-D365-YTD-compressed-2017.txt` (keep the original in Google Drive; the local working copy is in this path).
- Generated results: `outputs/` (ignored by Git).

## Exact audit command

Run from the project root with the project-local Conda environment:

```sh
.venv/bin/python scripts/audit_harvey_311.py \
  data/raw/311-CRIS-Public-Data-Extract-D365-YTD-compressed-2017.txt \
  data/processed/geography/houston_grid.gpkg \
  outputs/harvey \
  2017-08-25 2017-09-08
```

## Interpreter setup on this Mac

The system Python (`/usr/bin/python3`) and Homebrew Python 3.13 did not have `osgeo`. Miniforge was installed and a project-local Conda environment was created at `.venv/` with Python 3.12 and GDAL 3.13.3 from conda-forge. `.venv/bin/python` successfully imports `ogr` and `osr` and opens the GPKG driver. The environment is ignored by Git.

## Filtered output

`scripts/filter_harvey_311.py` reuses the audit's projected point-to-grid join and produces one row for every cell in `data/processed/harvey_311_grid_counts.csv`. `outputs/qa/harvey/reconciliation.json` records unique request totals, rule-level counts, and joined/invalid/outside outcomes. `outputs/qa/harvey/keyword_match_audit.csv` preserves request IDs and all matched rule IDs; rule totals can overlap, while the per-cell additions count each request once. `outputs/qa/harvey/daily_keyword_comparison.csv` contains 28 preceding days and 14 event days. The configurable storm name and four rules are in `config/harvey_filter.json`. Matching normalizes whitespace, uses case-insensitive word boundaries, and screens explicit negations. Automatic categories qualify with blank descriptions.

With the expanded shared automatic categories, the category-only baseline is **8,386 requests**: 1,745 Flooding, 1,742 Storm Debris Collection, 804 Crisis Cleanup, 950 Street Hazard, 191 Tree Removal, 140 Street Condition, 1,718 Traffic Signal Maintenance, 208 Traffic Signals, and 888 Water Leak. Of these, 8,156 join the grid, 102 have invalid coordinates, and 128 fall outside Houston.

The text rules then add 93 unique requests in the event window; 89 join the grid, two have invalid coordinates, and two are outside Houston. The combined total is **8,245 in-grid requests** (8,479 qualifying before joining). The 28-day prior window has one keyword candidate. Earlier trial keyword counts predate these categories becoming automatic and should not be compared directly with the current keyword-added counts.
