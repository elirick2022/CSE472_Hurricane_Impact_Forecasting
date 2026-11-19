# Houston impact model progress log

## November 19, 2026

| Decision | Why | Status |
|---|---|---|
| Use Houston’s full-purpose limits as the working footprint | The city GIS layer distinguishes full-purpose and limited-purpose service areas. Full-purpose limits give us a reproducible municipal footprint for a Houston 311 model. | Built from a current snapshot. Historical 311 service and annexation differences still need verification. |
| Keep a fixed projected 1 km lattice | A single lattice aligns all storms and predictors. NAD83 / UTM zone 15N (EPSG:26915) gives metre coordinates. IDs use lattice indices referenced to projected origin (0,0), so they stay stable across joins. | Validated 2,127 unique positive-area cells. Of these, 1,234 are full and 893 are clipped. Summed area matches the dissolved footprint at 1,551.217447 km². |
| Preserve actual clipped areas and aggregate multipart fragments under one cell ID | A city-edge cell may cover a fraction of a square kilometre or contain disconnected pieces. Retaining the measured area preserves an appropriate denominator for intensity. | Grid and boundary are separate layers in `houston_grid.gpkg`. One input geometry required repair for nested shells before dissolution. |
| Use the 2017 annual 311 extract as the Harvey source | Annual extracts support a common approach across storms and can supply a pre-storm baseline. | This read reproduced 381,559 parsed requests, 11 embedded headers, and one malformed record. Its location is recorded in the audit. UTC dates extend into Jan 1, 2018, consistent with converting late local times across midnight. |
| Use Aug 25–Sep 7 UTC for the provisional join | The closest available fix in the supplied Harvey track is Aug 28 at 18:00 UTC. Applying the working −3 through +10 day rule gives this window. A bounded run lets us check the pipeline before settling the storm-label definition. | Aug 25 00:00 inclusive through Sep 8 00:00 exclusive. Revisit the anchor and windows during the joint review. |
| Test the spatial join using every category in that window | We can verify geometry, coordinates and reconciliation now. The category totals also show where reviewing the 311 labels will matter most. | Of 17,690 requests, 17,340 joined to distinct grid assignments, 173 had invalid coordinates and 177 were outside the footprint. The map includes every cell. Displayed zero means zero assignments in this test. |
| Apply shared automatic categories across storms | Flooding, debris, hazards, traffic signals, and water leaks are reasonable service-impact categories even when descriptions are blank. | `config/event_category_rules.csv` now automatically includes Flooding, Storm Debris Collection, Crisis Cleanup, Street Hazard, Tree Removal, Street Condition, Traffic Signal Maintenance, Traffic Signals, and Water Leak for both Harvey and Nicholas. Nicholas retains its three additional event-specific categories. Both event outputs have been rerun and reconciled to the fixed grid. |

### Next filtering review

1. Review samples from the newly automatic categories to track category-level precision across storms.
2. Review text-rule matches and exclusions, especially categories that remain conditional on description evidence.
3. Continue validating predictors and event windows, then reconcile target counts per eligible grid cell.

### Sources and reproduction

The boundary snapshot was retrieved November 19, 2026 from [City of Houston COH_Limits, layer 0](https://services.arcgis.com/su8ic9KbA7PYVxPS/ArcGIS/rest/services/COH_Limits/FeatureServer/0). The query returned two features for `SERVICE_TY='FULL'`, matching the service count. The source GeoJSON uses longitude and latitude in EPSG:4326 and is included in the project package. Boundary SHA-256 is `f6fb31d82f1880b40c51f89cb22d0f9173dc104a51938ab9fe4c3713a5ebe9d4`.

The [2017 annual Houston 311 extract](https://drive.google.com/file/d/1TgLrvL1YAH73gESiir-9vtW9ToGfx2Xl/view) is 243,434,623 bytes and has SHA-256 `6e50e804fa5b075670e8988f36f5352ec63654b54ae342c0c444f0ecc3f5a565`. The [Harvey track](https://drive.google.com/file/d/1PXSrKVnDuXjJFAtGsiES70qMudZjjVYP/view) supplied the provisional anchor. The package contains the aggregate audit, category review table, per-cell diagnostic counts, projected map and processing scripts. The scripts list their command-line inputs.
