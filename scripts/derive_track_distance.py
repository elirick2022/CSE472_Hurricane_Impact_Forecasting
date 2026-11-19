"""Extract NHC best tracks and derive closest distance on the fixed grid.

Run from the project root with GDAL's Python bindings:
.venv/bin/python scripts/derive_track_distance.py \
  data/processed/geography/houston_grid.gpkg
"""
import csv
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from osgeo import ogr, osr

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_TRACKS = PROJECT_ROOT / 'data/raw/weather/tracks'
PROCESSED_WEATHER = PROJECT_ROOT / 'data/processed/weather'
EVENTS = {
    'AL092017': ('Harvey', '2017-08-28'),
    'AL142021': ('Nicholas', '2021-09-14'),
    'AL022024': ('Beryl', '2024-07-08'),
}
RADII = [f'r{speed}_{quadrant}_nm' for speed in (34, 50, 64)
         for quadrant in ('ne', 'se', 'sw', 'nw')]
FIELDS = ['storm_id', 'fix_utc', 'record', 'status', 'lat', 'lon',
          'max_wind_kt', 'min_pressure_hpa', *RADII, 'rmw_nm']


def position(value):
    return float(value[:-1]) * (-1 if value[-1] in 'SW' else 1)


def read_track(archive):
    records = {event: [] for event in EVENTS}
    storm = None
    with archive.open(newline='') as file:
        for row in csv.reader(file, skipinitialspace=True):
            if row[0].startswith('AL'):
                storm = row[0]
                continue
            if storm not in EVENTS:
                continue
            fix = datetime.strptime(row[0] + row[1], '%Y%m%d%H%M').replace(tzinfo=timezone.utc)
            numbers = [None if v == '-999' else int(v) for v in row[6:21]]
            records[storm].append([storm, fix, row[2], row[3],
                                   position(row[4]), position(row[5]), *numbers])
    return records


def write_csv(path, header, values):
    with path.open('w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(values)


def track_geometry(rows, start, end, transform):
    line = ogr.Geometry(ogr.wkbLineString)
    for left, right in zip(rows, rows[1:]):
        first, last = left[1], right[1]
        overlap_start, overlap_end = max(first, start), min(last, end)
        if overlap_start >= overlap_end:
            continue
        for instant in (overlap_start, overlap_end):
            fraction = (instant - first) / (last - first)
            lat = left[4] + fraction * (right[4] - left[4])
            lon = left[5] + fraction * (right[5] - left[5])
            x, y, _ = transform.TransformPoint(lon, lat)
            if line.GetPointCount() == 0 or line.GetPoint(line.GetPointCount()-1)[:2] != (x, y):
                line.AddPoint_2D(x, y)
    if line.GetPointCount() < 2:
        raise ValueError('No track segments overlap the weather window')
    return line


def main(grid_path, output_path=None):
    ogr.UseExceptions()
    dataset = ogr.Open(grid_path)
    layer = dataset.GetLayerByName('grid_1km')
    source = osr.SpatialReference()
    source.ImportFromEPSG(4326)
    target = layer.GetSpatialRef()
    for srs in (source, target):
        srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    transform = osr.CoordinateTransformation(source, target)
    points = [(feature['cell_id'], feature.GetGeometryRef().PointOnSurface()) for feature in layer]
    tracks = read_track(RAW_TRACKS / 'hurdat2-1851-2025-092326.txt')
    distances = []
    processed_tracks = PROCESSED_WEATHER / 'tracks'
    processed_tracks.mkdir(parents=True, exist_ok=True)
    for storm, (name, anchor) in EVENTS.items():
        rows = tracks[storm]
        write_csv(processed_tracks / f'{name.lower()}_best_track.csv', FIELDS, rows)
        day = datetime.fromisoformat(anchor).replace(tzinfo=timezone.utc)
        start, end = day - timedelta(days=3), day + timedelta(days=4)
        line = track_geometry(rows, start, end, transform)
        block = [(storm, cell, round(point.Distance(line) / 1000, 6)) for cell, point in points]
        assert len(block) == len({r[1] for r in block}) == 2127
        distances.extend(block)
        print(name, start.date(), end.date(), len(rows), sum(r[-1] is not None for r in rows),
              min(r[-1] for r in block), max(r[-1] for r in block))
    output_path = Path(output_path) if output_path else PROCESSED_WEATHER / 'track_distance_by_cell.csv'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_csv(output_path, ['storm_id', 'cell_id', 'track_min_km'], distances)
    print('Wrote', output_path)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
