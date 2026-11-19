"""Apply configured description rules and aggregate 311 requests to the Houston grid."""
import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from osgeo import ogr, osr


def read_categories(path):
    with path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    categories = {
        row["category"].strip()
        for row in rows
        if row["rule"].strip() == "automatic_include"
        and row["status"].strip().lower() == "approved"
    }
    if not categories:
        raise ValueError(f"No approved automatic_include categories in {path}")
    return categories


def normalize(text):
    return re.sub(r"\s+", " ", text).strip()


def compile_term(term):
    words = re.split(r"\s+", normalize(term))
    return re.compile(r"(?<!\w)" + r"\s+".join(map(re.escape, words)) + r"(?!\w)", re.IGNORECASE)


def is_negated(text, start, negation_words):
    if not negation_words:
        return False
    prefix = text[:start]
    words = "|".join(re.escape(word) for word in negation_words)
    return re.search(r"(?:^|\b)(?:" + words + r")\b(?:\s+\w+){0,3}\s+$", prefix, re.IGNORECASE) is not None


def positive_matches(text, term, negation_words):
    pattern = compile_term(term)
    return [match for match in pattern.finditer(text)
            if not is_negated(text, match.start(), negation_words)]


def rule_matches(rule, description, storm_name, negation_words, storm_name_phrases=None):
    kind = rule["type"]
    if kind == "storm_name":
        # The configurable name itself matches in phrases such as
        # "Hurricane Harvey", "Harvey-related", "after Harvey", etc.
        phrases = storm_name_phrases or [storm_name]
        return any(positive_matches(description, phrase, negation_words) for phrase in phrases)
    if kind == "any_phrase":
        return any(positive_matches(description, phrase, negation_words)
                   for phrase in rule["phrases"])
    if kind == "all_groups":
        return all(any(positive_matches(description, term, negation_words)
                       for term in group)
                   for group in rule["groups"])
    raise ValueError(f"Unsupported filter rule type: {kind}")


def rule_applies(rule, category):
    categories = rule["categories"]
    return categories == "all_other" or category in categories


def join_point(lon, lat, projection, cells):
    try:
        lon, lat = float(lon), float(lat)
    except ValueError:
        return "invalid", None
    if not (-180 <= lon <= 180 and -90 <= lat <= 90 and lon and lat):
        return "invalid", None
    x, y, _ = projection.TransformPoint(lon, lat)
    col, row = math.floor(x / 1000), math.floor(y / 1000)
    point = ogr.Geometry(ogr.wkbPoint)
    point.AddPoint_2D(x, y)
    matches = []
    # Same edge-aware indexed-cell join as audit_harvey_311.py.
    for key in ((col, row), (col - 1, row), (col, row - 1), (col - 1, row - 1)):
        if key in cells:
            cell_id, geometry = cells[key]
            if geometry.Intersects(point):
                matches.append(cell_id)
    return ("joined", min(matches)) if matches else ("outside", None)


def write_grid(path, cell_ids, baseline, added):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(("cell_id", "category_only_count", "keyword_added_count", "combined_count"))
        for cell_id in sorted(cell_ids):
            category_count = baseline[cell_id]
            keyword_count = added[cell_id]
            writer.writerow((cell_id, category_count, keyword_count, category_count + keyword_count))


def main(raw_path, grid_path, category_path, config_path, output_path,
         summary_path, daily_path, matches_path, start, end_exclusive):
    automatic = read_categories(category_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    automatic.update(normalize(category) for category in config.get("additional_automatic_categories", []))
    storm_name = normalize(config["storm_name"])
    storm_name_phrases = [normalize(p) for p in config.get("storm_name_phrases", [storm_name])]
    rules = config["rules"]
    negation_words = config.get("negation_words", ["no", "not", "never", "without"])
    for rule in rules:
        if rule_applies(rule, "__validation_category__") and rule["categories"] == "all_other":
            continue
        if rule.get("categories") != "all_other" and not isinstance(rule.get("categories"), list):
            raise ValueError(f"Rule {rule.get('id')} needs categories or all_other")

    ogr.UseExceptions()
    dataset = ogr.Open(str(grid_path))
    if dataset is None:
        raise OSError(f"Could not open grid: {grid_path}")
    layer = dataset.GetLayerByName("grid_1km")
    target = layer.GetSpatialRef()
    target.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    source = osr.SpatialReference()
    source.ImportFromEPSG(4326)
    source.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    projection = osr.CoordinateTransformation(source, target)
    cells = {
        (feature["grid_col"], feature["grid_row"]):
            (feature["cell_id"], feature.GetGeometryRef().Clone())
        for feature in layer
    }
    cell_ids = {value[0] for value in cells.values()}
    category_counts, keyword_counts = Counter(), Counter()
    baseline_by_cell, keyword_by_cell = Counter(), Counter()
    rule_counts = defaultdict(Counter)
    unique_candidates = {"event": set(), "prior": set()}
    negation_suppressed = {"event": set(), "prior": set()}
    prior_auto_keyword_candidates = set()
    daily_counts = {"event": Counter(), "prior": Counter()}
    id_match_rows = []
    seen = set()
    stats = Counter()
    period_requests = Counter()
    period_other_category_requests = Counter()
    prior_start = start - timedelta(days=28)
    prior_end = start
    window_start, window_end = prior_start, end_exclusive

    with raw_path.open(encoding="utf-8-sig", errors="replace") as input_file:
        fields = None
        for line_number, line in enumerate(input_file, start=1):
            values = line.rstrip("\r\n").split("|")
            if fields is None:
                candidate = [field.strip() for field in values]
                required = {"365 Case Number", "Created Date UTC", "Longitude", "Latitude",
                            "Incident Case Type", "Description"}
                if required.issubset(candidate):
                    fields = candidate
                continue
            if [field.strip() for field in values] == fields or not line.strip():
                continue
            if len(values) != len(fields):
                stats["malformed_rows"] += 1
                continue
            stats["parsed_annual"] += 1
            record = dict(zip(fields, values))
            case_id = record["365 Case Number"].strip()
            if not case_id or case_id in seen:
                stats["missing_or_duplicate_case_ids"] += 1
                continue
            seen.add(case_id)
            try:
                day = date.fromisoformat(record["Created Date UTC"].strip()[:10])
            except ValueError:
                stats["invalid_utc_dates"] += 1
                continue
            if not window_start <= day < window_end:
                continue
            period = "event" if start <= day < end_exclusive else "prior"
            category = record["Incident Case Type"].strip() or "(blank)"
            period_requests[period] += 1
            if category not in automatic:
                period_other_category_requests[period] += 1
            if period == "event" and category in automatic:
                category_counts[category] += 1
                stats["category_only_candidates"] += 1
                join_status, cell_id = join_point(record["Longitude"], record["Latitude"], projection, cells)
                if join_status == "joined":
                    baseline_by_cell[cell_id] += 1
                    stats["category_only_joined"] += 1
                else:
                    stats[f"category_only_{join_status}"] += 1
                continue
            if category in automatic:
                # Automatic categories define the event baseline; they are
                # not reintroduced as description-only candidates in either period.
                description = normalize(record["Description"])
                if description and any(
                    rule.get("categories") == "all_other"
                    and rule_matches(rule, description, storm_name, negation_words, storm_name_phrases)
                    for rule in rules
                ):
                    prior_auto_keyword_candidates.add(case_id)
                continue

            description = normalize(record["Description"])
            if not description:
                continue
            applicable_rules = [rule for rule in rules if rule_applies(rule, category)]
            unfiltered_rule_ids = [rule["id"] for rule in applicable_rules
                                   if rule_matches(rule, description, storm_name, [], storm_name_phrases)]
            matched_rule_ids = [rule["id"] for rule in applicable_rules
                                if rule_matches(rule, description, storm_name, negation_words, storm_name_phrases)]
            if unfiltered_rule_ids and not matched_rule_ids:
                negation_suppressed[period].add(case_id)
            if not matched_rule_ids:
                continue

            unique_candidates[period].add(case_id)
            daily_counts[period][day] += 1
            keyword_counts[(period, category)] += 1
            join_status, cell_id = join_point(record["Longitude"], record["Latitude"], projection, cells)
            for rule_id in matched_rule_ids:
                rule_counts[(period, category, rule_id)]["candidates"] += 1
                rule_counts[(period, category, rule_id)][join_status] += 1
            if period == "event":
                if join_status == "joined":
                    keyword_by_cell[cell_id] += 1
                    stats["keyword_joined"] += 1
                else:
                    stats[f"keyword_{join_status}"] += 1
                id_match_rows.append((case_id, str(day), category, ";".join(matched_rule_ids), join_status, cell_id or ""))

    if fields is None:
        raise ValueError("Could not find expected annual extract header")
    if len(cell_ids) != 2127:
        raise AssertionError(f"Expected the fixed 2,127-cell Houston grid, found {len(cell_ids)}")
    if sum(baseline_by_cell.values()) != stats["category_only_joined"]:
        raise AssertionError("Per-cell category-only counts do not reconcile to joined requests")
    if sum(keyword_by_cell.values()) != stats["keyword_joined"]:
        raise AssertionError("Per-cell keyword counts do not reconcile to joined requests")
    write_grid(output_path, cell_ids, baseline_by_cell, keyword_by_cell)

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    rule_summary = []
    for (period, category, rule_id), counts in sorted(rule_counts.items()):
        rule_summary.append({"period": period, "category": category, "rule_id": rule_id,
                             "unique_candidates": counts["candidates"],
                             "joined_to_grid": counts["joined"],
                             "invalid_coordinates": counts["invalid"],
                             "outside_houston": counts["outside"]})
    report = {
        "event_window": {"start_utc_inclusive": str(start),
                         "end_utc_inclusive": str(end_exclusive - timedelta(days=1)),
                         "end_utc_exclusive": str(end_exclusive)},
        "prior_window": {"start_utc_inclusive": str(prior_start),
                         "end_utc_inclusive": str(prior_end - timedelta(days=1)),
                         "end_utc_exclusive": str(prior_end)},
        "automatic_categories": sorted(automatic),
        "storm_name": storm_name,
        "storm_name_phrases": storm_name_phrases,
        "rules": rules,
        "negation_words": negation_words,
        "unique_keyword_candidates": {
            "event": len(unique_candidates["event"]),
            "prior": len(unique_candidates["prior"])
        },
        "keyword_match_rates": {
            period: {
                "unique_keyword_candidates": len(unique_candidates[period]),
                "all_unique_requests_in_window": period_requests[period],
                "all_request_rate": (len(unique_candidates[period]) / period_requests[period]
                                     if period_requests[period] else 0),
                "nonautomatic_unique_requests_in_window": period_other_category_requests[period],
                "nonautomatic_request_rate": (len(unique_candidates[period]) / period_other_category_requests[period]
                                               if period_other_category_requests[period] else 0)
            }
            for period in ("event", "prior")
        },
        "category_only_candidates_by_category": {
            category: count for category, count in sorted(category_counts.items())
        },
        "keyword_candidates_by_period_and_category": [
            {"period": period, "category": category, "unique_candidates": count}
            for (period, category), count in sorted(keyword_counts.items())
        ],
        "negation_screen": {
            "otherwise_matching_requests_excluded": {
                "event": len(negation_suppressed["event"]),
                "prior": len(negation_suppressed["prior"])
            },
            "prior_window_automatic_category_requests_that_match_text_rules": len(prior_auto_keyword_candidates)
        },
        "category_only_baseline": {
            "candidates": stats["category_only_candidates"],
            "joined_to_grid": stats["category_only_joined"],
            "invalid_coordinates": stats["category_only_invalid"],
            "outside_houston": stats["category_only_outside"]
        },
        "event_keyword_additions": {
            "unique_candidates_before_spatial_join": len(unique_candidates["event"]),
            "joined_to_grid": stats["keyword_joined"],
            "invalid_coordinates": stats["keyword_invalid"],
            "outside_houston": stats["keyword_outside"]
        },
        "unique_keyword_matches_by_category_and_rule": rule_summary,
        "rule_totals_may_overlap": True,
        "grid_cells": len(cell_ids),
        "grid_cells_with_keyword_additions": sum(keyword_by_cell[c] > 0 for c in cell_ids),
        "combined_qualifying_before_spatial_join": stats["category_only_candidates"] + len(unique_candidates["event"]),
        "combined_in_grid_total": stats["category_only_joined"] + stats["keyword_joined"],
        "combined_spatial_reconciliation": {
            "qualifying_before_spatial_join": stats["category_only_candidates"] + len(unique_candidates["event"]),
            "joined_to_grid": stats["category_only_joined"] + stats["keyword_joined"],
            "invalid_coordinates": stats["category_only_invalid"] + stats["keyword_invalid"],
            "outside_houston": stats["category_only_outside"] + stats["keyword_outside"],
            "reconciles": (stats["category_only_candidates"] + len(unique_candidates["event"])
                           == stats["category_only_joined"] + stats["keyword_joined"]
                           + stats["category_only_invalid"] + stats["keyword_invalid"]
                           + stats["category_only_outside"] + stats["keyword_outside"])
        },
        "per_cell_sum_verified": True,
        "parse_stats": dict(stats)
    }
    summary_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    daily_path.parent.mkdir(parents=True, exist_ok=True)
    with daily_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(("period", "utc_date", "unique_keyword_matches"))
        for period, first, last in (("prior", prior_start, prior_end), ("event", start, end_exclusive)):
            day = first
            while day < last:
                writer.writerow((period, day.isoformat(), daily_counts[period][day]))
                day += timedelta(days=1)

    matches_path.parent.mkdir(parents=True, exist_ok=True)
    with matches_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(("case_id", "utc_date", "category", "matched_rule_ids", "spatial_status", "cell_id"))
        writer.writerows(id_match_rows)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]),
         Path(sys.argv[5]), Path(sys.argv[6]), Path(sys.argv[7]), Path(sys.argv[8]),
         date.fromisoformat(sys.argv[9]), date.fromisoformat(sys.argv[10]))
