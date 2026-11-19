"""Usage: .venv/bin/python scripts/subset_tiger.py GRID.gpkg TIGER_ZIP_DIR OUTPUT.gpkg"""
from collections import Counter
from pathlib import Path
import sys
from osgeo import ogr, osr

ogr.UseExceptions()
grid = ogr.Open(sys.argv[1])
limits = grid.GetLayerByName('full_purpose_boundary')
city_feature = limits.GetNextFeature()
city = city_feature.GetGeometryRef()
city_crs = limits.GetSpatialRef()
city_crs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
out = ogr.GetDriverByName('GPKG').CreateDataSource(sys.argv[3])
for year in (2015, 2019, 2022):
    archive = Path(sys.argv[2]).resolve() / f'tl_{year}_48_bg.zip'
    source = ogr.Open('/vsizip/' + str(archive))
    layer = source.GetLayer()
    crs = layer.GetSpatialRef()
    crs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    transform = osr.CoordinateTransformation(crs, city_crs)
    city_in_source = city.Clone()
    city_in_source.Transform(osr.CoordinateTransformation(city_crs, crs))
    west, east, south, north = city_in_source.GetEnvelope()
    layer.SetSpatialFilterRect(west, south, east, north)
    dest = out.CreateLayer(f'bg_{year}', crs, ogr.wkbMultiPolygon)
    for field in ('GEOID', 'COUNTYFP'):
        dest.CreateField(ogr.FieldDefn(field, ogr.OFTString))
    counties = Counter()
    covered = 0
    dest.StartTransaction()
    for feature in layer:
        original = feature.GetGeometryRef()
        projected = original.Clone()
        projected.Transform(transform)
        if not projected.IsValid():
            projected = projected.MakeValid()
        if not projected.Intersects(city):
            continue
        area = projected.Intersection(city).GetArea()
        if area <= 0:
            continue
        covered += area
        result = ogr.Feature(dest.GetLayerDefn())
        for field in ('GEOID', 'COUNTYFP'):
            result.SetField(field, feature[field])
        result.SetGeometry(ogr.ForceToMultiPolygon(original.Clone()))
        dest.CreateFeature(result)
        counties[feature['COUNTYFP']] += 1
    dest.CommitTransaction()
    print(year, sum(counties.values()), dict(counties), covered / city.GetArea())
