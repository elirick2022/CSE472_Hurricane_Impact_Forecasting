"""Audit the annual 311 extract and reconcile a provisional all-category join.

Usage: /usr/bin/python3 audit_harvey_311.py RAW.txt GRID.gpkg OUTPUT_DIR START END
START and END are UTC dates, with END exclusive. Results contain aggregates.
"""
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from osgeo import ogr, osr


def save_csv(path, headings, rows):
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(headings)
        writer.writerows(rows)


def main(raw, grid_path, output, start, end):
    ogr.UseExceptions()
    dataset = ogr.Open(grid_path)
    layer = dataset.GetLayerByName("grid_1km")
    target = layer.GetSpatialRef()
    target.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    source = osr.SpatialReference()
    source.ImportFromEPSG(4326)
    source.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    projection = osr.CoordinateTransformation(source, target)
    cells = {
        (f["grid_col"], f["grid_row"]): (f["cell_id"], f.GetGeometryRef().Clone())
        for f in layer
    }
    summary, daily, spatial = Counter(), Counter(), Counter()
    categories = defaultdict(Counter)
    seen = set()
    malformed = []
    dates = set()
    with open(raw, encoding="utf-8-sig", errors="replace") as input_file:
        fields = None
        for line_number, line in enumerate(input_file, start=1):
            values = line.rstrip("\r\n").split("|")
            if fields is None:
                candidate = [field.strip() for field in values]
                if {"365 Case Number", "Created Date UTC", "Longitude"}.issubset(candidate):
                    fields = candidate
                continue
            if [field.strip() for field in values] == fields:
                summary["repeated_headers"] += 1
                continue
            if not line.strip():
                continue
            if len(values) != len(fields):
                malformed.append({"line": line_number, "fields": len(values)})
                continue
            summary["parsed_annual"] += 1
            record = dict(zip(fields, values))
            case_id = record["365 Case Number"].strip()
            if not case_id or case_id in seen:
                summary["missing_or_duplicate_case_ids"] += 1
                continue
            seen.add(case_id)
            try:
                day = date.fromisoformat(record["Created Date UTC"].strip()[:10])
            except ValueError:
                summary["invalid_utc_dates"] += 1
                continue
            dates.add(day)
            if not start <= day < end:
                continue
            daily[day] += 1
            category = record["Incident Case Type"].strip() or "(blank)"
            review = categories[category]
            review["all_requests"] += 1
            review["with_description"] += bool(record["Description"].strip())
            try:
                lon, lat = float(record["Longitude"]), float(record["Latitude"])
            except ValueError:
                lon, lat = 0, 0
            if not (-180 <= lon <= 180 and -90 <= lat <= 90 and lon and lat):
                review["invalid_coordinates"] += 1
                continue
            x, y, _ = projection.TransformPoint(lon, lat)
            col, row = math.floor(x / 1000), math.floor(y / 1000)
            point = ogr.Geometry(ogr.wkbPoint)
            point.AddPoint_2D(x, y)
            # Only the indexed square and its western/southern neighbors can
            # contain a point. Include touching cells for stable edge tie breaks.
            matches = []
            for key in ((col, row), (col-1, row), (col, row-1), (col-1, row-1)):
                if key in cells:
                    cell_id, geometry = cells[key]
                    if geometry.Intersects(point):
                        matches.append(cell_id)
            if matches:
                spatial[min(matches)] += 1
                review["assigned_to_grid"] += 1
            else:
                review["outside_grid"] += 1
    assert fields and dates and daily
    status = sum((row for row in categories.values()), Counter())
    assert status["all_requests"] == sum(daily.values())
    assert status["assigned_to_grid"] == sum(spatial.values())
    assert sum(status[key] for key in ("invalid_coordinates", "assigned_to_grid", "outside_grid")) == sum(daily.values())
    output.mkdir(parents=True, exist_ok=True)
    columns = ("all_requests", "with_description", "invalid_coordinates", "outside_grid", "assigned_to_grid")
    save_csv(output / "harvey_category_review.csv", ("category", *columns),
             ((name, *(counts[col] for col in columns))
              for name, counts in sorted(categories.items(), key=lambda item: (-item[1]["all_requests"], item[0]))))
    save_csv(output / "harvey_all_category_qa.csv", ("cell_id", "all_category_qa_count"),
             ((cell_id, spatial[cell_id]) for cell_id in sorted(cell[0] for cell in cells.values())))
    save_csv(output / "harvey_daily_qa.csv", ("utc_date", "all_requests"), sorted(daily.items()))
    report = dict(summary, start_utc=str(start), end_utc_exclusive=str(end),
                  annual_utc_range=[str(min(dates)), str(max(dates))],
                  malformed_rows=malformed, provisional_window=dict(status),
                  category_count=len(categories), grid_cells=len(cells),
                  grid_cells_with_any_request=len(spatial))
    (output / "harvey_audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], Path(sys.argv[3]),
         date.fromisoformat(sys.argv[4]), date.fromisoformat(sys.argv[5]))
