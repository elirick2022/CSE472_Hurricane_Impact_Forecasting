"""Build the Houston lattice from an official full-purpose GeoJSON export.

Usage: /usr/bin/python3 prepare_houston_grid.py SOURCE.geojson OUTPUT_DIR
Requires GDAL Python bindings with GEOS. The source must be preselected to
full-purpose limits. The GeoPackage uses EPSG:26915 throughout.
"""
import json
import math
import sys
from pathlib import Path

from osgeo import ogr, osr


def polygon_parts(geometry):
    if geometry.GetGeometryName() == "POLYGON":
        if geometry.GetArea() > 0:
            yield geometry
    elif geometry.GetGeometryName() in {"MULTIPOLYGON", "GEOMETRYCOLLECTION"}:
        for child in geometry:
            yield from polygon_parts(child)


def write_feature(layer, geometry, **fields):
    feature = ogr.Feature(layer.GetLayerDefn())
    feature.SetGeometry(geometry)
    for key, value in fields.items():
        feature.SetField(key, value)
    if layer.CreateFeature(feature):
        raise RuntimeError("Could not write feature")


def main(source_path, output):
    ogr.UseExceptions()
    source = ogr.Open(source_path)
    source_layer = source.GetLayer()
    source_srs = source_layer.GetSpatialRef()
    source_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    projected = osr.SpatialReference()
    projected.ImportFromEPSG(26915)
    projected.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    project = osr.CoordinateTransformation(source_srs, projected)
    polygons = ogr.Geometry(ogr.wkbMultiPolygon)
    for feature in source_layer:
        geometry = feature.GetGeometryRef().Clone()
        geometry.Transform(project)
        if not geometry.IsValid():
            geometry = geometry.MakeValid()
        for part in polygon_parts(geometry):
            polygons.AddGeometry(part)
    dissolved = polygons.UnionCascaded()
    assert dissolved and dissolved.IsValid() and dissolved.GetArea() > 0
    boundary = ogr.ForceToMultiPolygon(dissolved)
    output.mkdir(parents=True, exist_ok=True)
    path = output / "houston_grid.gpkg"
    if path.exists():
        raise FileExistsError(path)
    dataset = ogr.GetDriverByName("GPKG").CreateDataSource(str(path))
    limits = dataset.CreateLayer("full_purpose_boundary", projected, ogr.wkbMultiPolygon)
    write_feature(limits, boundary)
    grid = dataset.CreateLayer("grid_1km", projected, ogr.wkbMultiPolygon)
    for name, datatype in (("cell_id", ogr.OFTString), ("grid_col", ogr.OFTInteger),
                           ("grid_row", ogr.OFTInteger), ("area_km2", ogr.OFTReal)):
        grid.CreateField(ogr.FieldDefn(name, datatype))
    west, east, south, north = boundary.GetEnvelope()
    total = 0.0
    ids = set()
    full = 0
    grid.StartTransaction()
    for col in range(math.floor(west / 1000), math.ceil(east / 1000)):
        for row in range(math.floor(south / 1000), math.ceil(north / 1000)):
            x, y = col * 1000, row * 1000
            ring = ogr.Geometry(ogr.wkbLinearRing)
            for px, py in ((x, y), (x+1000, y), (x+1000, y+1000), (x, y+1000), (x, y)):
                ring.AddPoint_2D(px, py)
            square = ogr.Geometry(ogr.wkbPolygon)
            square.AddGeometry(ring)
            if not square.Intersects(boundary):
                continue
            clipped = ogr.Geometry(ogr.wkbMultiPolygon)
            for part in polygon_parts(square.Intersection(boundary)):
                clipped.AddGeometry(part)
            area = clipped.GetArea() / 1e6
            if area <= 0:
                continue
            cell_id = f"HOU_{col}_{row}"
            assert cell_id not in ids and clipped.IsValid() and area <= 1 + 1e-9
            write_feature(grid, clipped, cell_id=cell_id, grid_col=col, grid_row=row, area_km2=area)
            ids.add(cell_id)
            total += area
            full += math.isclose(area, 1, abs_tol=1e-9)
    grid.CommitTransaction()
    boundary_area = boundary.GetArea() / 1e6
    assert math.isclose(total, boundary_area, abs_tol=1e-6)
    print(json.dumps({"input_features": source_layer.GetFeatureCount(), "cells": len(ids),
                      "full_cells": full, "clipped_cells": len(ids)-full,
                      "grid_area_km2": total, "boundary_area_km2": boundary_area}, indent=2))


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]))
