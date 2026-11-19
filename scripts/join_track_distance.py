"""Validate the track-distance table and attach distances to storm 311 grids."""
import csv
import hashlib
import json
from pathlib import Path

from osgeo import ogr


ROOT = Path(__file__).resolve().parents[1]
GRID_PATH = ROOT / "data/processed/geography/houston_grid.gpkg"
PACKAGE_TRACK_PATH = ROOT / "data/raw/weather/track_distance_by_cell.csv"
DERIVED_TRACK_PATH = ROOT / "data/processed/weather/track_distance_by_cell.csv"
STORMS = {
    "AL092017": ("Harvey", ROOT / "data/processed/harvey_311_grid_counts.csv",
                 ROOT / "data/processed/harvey/311_grid_with_track_distance.csv"),
    "AL142021": ("Nicholas", ROOT / "data/processed/nicholas/311_grid_counts.csv",
                 ROOT / "data/processed/nicholas/311_grid_with_track_distance.csv"),
}
TRACK_STORM_IDS = ("AL092017", "AL142021", "AL022024")
COUNT_FIELDS = ("category_only_count", "keyword_added_count", "combined_count")


def read_track(path):
    table = {}
    rows_by_storm = {}
    with path.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            key = (row["storm_id"], row["cell_id"])
            if key in table:
                raise ValueError(f"Duplicate track key in {path}: {key}")
            table[key] = float(row["track_min_km"])
            rows_by_storm[key[0]] = rows_by_storm.get(key[0], 0) + 1
    return table, rows_by_storm


def read_grid_ids():
    ogr.UseExceptions()
    dataset = ogr.Open(str(GRID_PATH))
    layer = dataset.GetLayerByName("grid_1km")
    return {feature["cell_id"] for feature in layer}


def read_cells(path):
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        rows = list(reader)
        fields = reader.fieldnames
    by_id = {row["cell_id"]: row for row in rows}
    if len(by_id) != len(rows):
        raise ValueError(f"Duplicate cell IDs in {path}")
    return fields, by_id


def inspect_source_inputs():
    weather_root = ROOT / "data/raw/weather"
    with (weather_root / "stage_iv_inventory.csv").open(newline="", encoding="utf-8") as file:
        inventory = list(csv.DictReader(file))
    stage_counts = {}
    stage_details = []
    for row in inventory:
        path = weather_root / row["path"]
        exists = path.is_file()
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if exists else None
        matches = digest == row["sha256"]
        if not exists or not matches:
            raise AssertionError(f"Stage IV inventory check failed for {path}")
        stage_counts[row["event"]] = stage_counts.get(row["event"], 0) + 1
        stage_details.append({"event": row["event"], "path": str(path.relative_to(ROOT)),
                              "sha256_matches_inventory": matches,
                              "inventory_status": row["status"]})

    hurdat = weather_root / "tracks/hurdat2-1851-2025-092326.txt"
    storm_tracks = {}
    for storm in ("harvey", "nicholas", "beryl"):
        track_path = weather_root / f"tracks/{storm}_best_track.csv"
        with track_path.open(newline="", encoding="utf-8") as file:
            storm_tracks[storm] = sum(1 for _ in csv.DictReader(file))

    tiger_path = ROOT / "data/raw/census/houston_tiger_block_groups.gpkg"
    tiger = ogr.Open(str(tiger_path))
    tiger_layers = {}
    for index in range(tiger.GetLayerCount()):
        layer = tiger.GetLayerByIndex(index)
        tiger_layers[layer.GetName()] = layer.GetFeatureCount()
    if tiger_layers != {"bg_2015": 1567, "bg_2019": 1566, "bg_2022": 1904}:
        raise AssertionError(f"Unexpected TIGER layer counts: {tiger_layers}")
    tiger_source_archives = [
        "tl_2015_48_bg.zip", "tl_2019_48_bg.zip", "tl_2022_48_bg.zip"
    ]
    return {
        "stage_iv": {"inventory_rows": len(inventory), "files_by_storm": stage_counts,
                     "all_files_exist_and_match_sha256": True, "files": stage_details},
        "tracks": {"hurdat2_archive": str(hurdat.relative_to(ROOT)),
                   "hurdat2_archive_exists": hurdat.is_file(),
                   "storm_track_rows": storm_tracks},
        "tiger_block_groups": {"path": str(tiger_path.relative_to(ROOT)),
                               "layers_by_block_group_vintage": tiger_layers,
                               "acs_estimates_joined": False},
        "not_included_inputs_or_products": {
            "subdaily_stage_iv_edge_data": "Needed for exact midnight-window rainfall totals; package provides noon-to-noon 24-hour files only.",
            "matching_acs_estimates": "Not included; TIGER GEOIDs still need a matching ACS estimate table and join.",
            "modeled_wind_predictors": "Not included; hourly local winds, peak gust, and cumulative exposure remain to be modeled.",
            "raw_tiger_source_archives": {name: (ROOT / "data/raw/census" / name).exists()
                                          for name in tiger_source_archives}
        }
    }


def main():
    grid_ids = read_grid_ids()
    if len(grid_ids) != 2127:
        raise AssertionError(f"Expected 2,127 grid IDs, found {len(grid_ids)}")
    package, package_counts = read_track(PACKAGE_TRACK_PATH)
    derived, derived_counts = read_track(DERIVED_TRACK_PATH)

    track_report = {}
    for source_name, table, counts in (("package", package, package_counts),
                                       ("derived", derived, derived_counts)):
        if set(counts) != set(TRACK_STORM_IDS):
            raise AssertionError(f"Unexpected storm IDs in {source_name} track table: {sorted(counts)}")
        for storm_id in TRACK_STORM_IDS:
            keys = {cell_id for key_storm, cell_id in table if key_storm == storm_id}
            if counts[storm_id] != 2127:
                raise AssertionError(f"{source_name} {storm_id} has {counts[storm_id]} rows")
            if keys != grid_ids:
                raise AssertionError(
                    f"{source_name} {storm_id} grid key mismatch: "
                    f"missing={len(grid_ids - keys)}, extra={len(keys - grid_ids)}"
                )
        track_report[source_name] = {
            "rows": len(table),
            "rows_per_storm": counts,
            "unique_composite_keys": len(table),
            "cell_ids_match_grid_for_every_storm": True
        }

    package_keys, derived_keys = set(package), set(derived)
    if package_keys != derived_keys:
        raise AssertionError(
            f"Reproduced track table key mismatch: package-only={len(package_keys-derived_keys)}, "
            f"derived-only={len(derived_keys-package_keys)}"
        )
    max_abs_delta = max(abs(package[key] - derived[key]) for key in package_keys)
    if max_abs_delta > 1e-6:
        raise AssertionError(f"Reproduced track distances differ by up to {max_abs_delta} km")

    joins = {}
    for storm_id, (name, source_path, output_path) in STORMS.items():
        fields, cells = read_cells(source_path)
        if len(cells) != 2127:
            raise AssertionError(f"{name} 311 table has {len(cells)} rows")
        missing_311 = grid_ids - set(cells)
        extra_311 = set(cells) - grid_ids
        if missing_311 or extra_311:
            raise AssertionError(
                f"{name} 311 grid key mismatch: missing={len(missing_311)}, extra={len(extra_311)}"
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sums_before = {field: sum(int(row[field]) for row in cells.values()) for field in COUNT_FIELDS}
        with output_path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=[*fields, "storm_id", "track_min_km"])
            writer.writeheader()
            for cell_id in sorted(cells):
                row = dict(cells[cell_id])
                row["storm_id"] = storm_id
                row["track_min_km"] = f"{derived[(storm_id, cell_id)]:.6f}"
                writer.writerow(row)
        fields_joined, joined = read_cells(output_path)
        sums_after = {field: sum(int(row[field]) for row in joined.values()) for field in COUNT_FIELDS}
        if len(joined) != len(cells) or sums_before != sums_after:
            raise AssertionError(f"{name} join changed its 311 row count or totals")
        joins[name] = {
            "input_rows": len(cells),
            "output_rows": len(joined),
            "unmatched_311_cell_ids": len(missing_311),
            "unmatched_track_cell_ids": 0,
            "311_totals_before": sums_before,
            "311_totals_after": sums_after,
            "output": str(output_path.relative_to(ROOT))
        }

    report = {
        "grid_cells": len(grid_ids),
        "source_inputs": inspect_source_inputs(),
        "track_distance_tables": track_report,
        "package_vs_reproduced": {
            "same_composite_keys": True,
            "max_absolute_distance_delta_km": max_abs_delta,
            "within_1e-6_km": max_abs_delta <= 1e-6
        },
        "311_joins": joins
    }
    report_path = ROOT / "outputs/qa/weather_census/reconciliation.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
