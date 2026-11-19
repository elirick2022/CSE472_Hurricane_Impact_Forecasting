# Hurricane Nicholas 311 processing

## Extract schema and coverage

The local source is `data/raw/311-CRIS-Public-Data-Extract-D365-YTD-compressed-2021.txt`. Its pipe-delimited schema includes `365 Case Number` (request ID), `Created Date UTC`, `Created Date Local`, `Latitude`, `Longitude`, `Incident Case Type`, and `Description`. The pipeline uses `Created Date UTC`; its values are timestamp strings without an offset, but the field explicitly identifies them as UTC. `Created Date Local` is Houston local wall time (CST/CDT), so it is not used for date selection. The scan found UTC timestamps from 2021-01-01 06:22:23 through 2022-01-01 05:29:06, and local timestamps from 2021-01-01 00:22:23 through 2021-12-31 23:29:06. This covers the event window and all 28 prior days.

There were 381,805 parsed unique request rows, two malformed rows, and no missing or duplicate request IDs. `Description` is present; 308,102 rows have text and 73,703 are blank. Coordinates are supplied in `Latitude` and `Longitude`.

## Event window

The same anchor method and window rule used for Harvey were applied: find the closest six-hour NHC best-track fix to a Houston reference point, then include three calendar days before through ten calendar days after the fix. For Nicholas, the closest listed fix is **2021-09-14 18:00 UTC**, at 29.6°N, 94.9°W, approximately 48.8 km from the Houston reference coordinate (29.7604°N, 95.3698°W). The anchor and rule yield **Sep 11 through Sep 24, 2021 UTC, inclusive** (end-exclusive boundary Sep 25 at 00:00 UTC). The pre-storm comparison is **Aug 14 through Sep 10, 2021 UTC, inclusive** (end-exclusive boundary Sep 11 at 00:00 UTC). The source is the [NHC Hurricane Nicholas Tropical Cyclone Report, Table 1](https://www.nhc.noaa.gov/data/tcr/AL142021_Nicholas.pdf), which gives best-track times and positions in UTC.

The event and storm phrase configuration is in `config/nicholas_event.json` and `config/nicholas_filter.json`. The four rule IDs and category scopes are the shared Harvey rules; the storm name and phrases are Nicholas-specific.

## Category comparison

`Flooding`, `Storm Debris Collection`, `Street Hazard`, `Tree Removal`, `Street Condition`, `Traffic Signal Maintenance`, `Traffic Signals`, and `Water Leak` have exact 2021 labels and are shared automatic includes for both storms. `Crisis Cleanup` is absent in all of 2021, so it contributes zero requests. Nicholas additionally automatically includes `Disaster Recovery Escalation`, `Severe Storm Tree Removal`, and `Spilled Debris`. These are Nicholas-only additions, not asserted label equivalents to Harvey categories. The event window has 14 Flooding, 492 Storm Debris Collection, 748 Street Hazard, 298 Tree Removal, 332 Street Condition, 1,926 Traffic Signal Maintenance, 181 Traffic Signals, 883 Water Leak, and five Spilled Debris requests. Disaster Recovery Escalation and Severe Storm Tree Removal have zero event requests; Disaster Recovery Escalation has one request in the prior window.

`Disaster Recovery Escalation` (three annual requests), `Spilled Debris` (298 annual), and `Severe Storm Tree Removal` (20 annual) remain distinct labels; their Nicholas-only automatic inclusion is a modeling decision, not a claim that they are equivalent to Crisis Cleanup or Storm Debris Collection. Traffic Signal Maintenance and Traffic Signals are now shared automatic includes. Sewer Wastewater and Sewer Manhole retain the shared conditional sewer-backup rule; Drainage is now a shared automatic include. No confirmed renamed equivalents were found. See `config/nicholas_category_mapping.csv` for annual and window counts and `outputs/qa/nicholas/schema_and_category_comparison.json` for the structured schema and mapping summary.

## Results

The category-only baseline contains **4,879 requests** across the eight shared automatic categories and the three Nicholas-only additions. Of those, 4,721 join the fixed grid, six have invalid coordinates, and 152 fall outside Houston. The per-category baseline counts are in the reconciliation JSON.

The filter finds 92 unique keyword candidates in the event window and 7 in the preceding 28 days. Using all unique requests as the rate denominator, the event match rate is **0.547%** (92/16,829) and the prior-window rate is **0.0239%** (7/29,329). Among nonautomatic categories only, the rates are 0.770% (92/11,950) and 0.0300% (7/23,318), respectively. Per-category/per-rule outcomes are in `outputs/qa/nicholas/reconciliation.json`; rule totals can overlap when a request matches more than one rule.

All 92 event-window keyword candidates join to the grid. The combined total is **4,971 qualifying requests**, of which **4,813 join the grid** (4,721 category-only + 92 keyword-added). `data/processed/nicholas/311_grid_counts.csv` contains all 2,127 fixed grid cells and retains their existing IDs; its combined-count sum is verified against the 4,813 in-grid qualifying requests. The daily comparison and request-level rule audit are saved under `outputs/qa/nicholas/`.

## Comparability notes

The 2021 extract has the same required request ID, UTC timestamp, coordinates, category, and description fields as the 2017 Harvey extract. The annual volume is 381,805 parsed rows versus 381,559 in 2017; the 2021 scan found two malformed rows versus one in the Harvey audit. UTC coverage rolls to Jan 1, 2022 because late local Dec 31 requests convert across midnight. Both event windows use 14 inclusive dates and a 28-day preceding window, but occur in different years. Category comparability is affected by the absent Crisis Cleanup label and the additional Nicholas-only categories. Description availability and category frequencies differ by year, so raw target counts should not be interpreted as a like-for-like storm severity comparison.
