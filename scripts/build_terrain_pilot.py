"""Create a traceable parking pilot layer and calculate bare-earth terrain metrics."""

import argparse
from pathlib import Path

import arcpy
from arcpy import sa


def run(root):
    gdb = root / "gis/snowpark/snowpark.gdb"
    source = str(gdb / "KSU_Parking_Combined_Candidates")
    pilot = str(gdb / "SnowPark_Surface_Pilot")
    arcpy.env.overwriteOutput = True
    crs = arcpy.SpatialReference(26917)
    if arcpy.Describe(source).spatialReference.factoryCode != crs.factoryCode:
        raise ValueError("Parking candidates must use EPSG:26917.")
    arcpy.conversion.ExportFeatures(
        source, pilot,
        "operator = 'Kent State University' AND parking = 'surface' "
        "AND F_id <> 'way/234637890' "
        "AND (review_status IS NULL OR review_status NOT IN ('Exclude', 'Needs verification'))",
    )
    count = int(arcpy.management.GetCount(pilot)[0])
    if not count:
        raise ValueError("The pilot contains no surfaces.")
    print(f"Pilot surfaces: {count}", flush=True)

    tiles = sorted((root / "data/raw/dem").glob("*.tif"))
    if len(tiles) != 2:
        raise ValueError("Expected the two Ohio 3DEP elevation tiles.")
    for tile in tiles:
        raster = arcpy.Raster(str(tile))
        print(f"{tile.name}: {raster.spatialReference.name}, cell {raster.meanCellWidth}", flush=True)
        if raster.spatialReference.factoryCode != 26917 or abs(raster.meanCellWidth - 1) > 0.01:
            raise ValueError("DEM must have a one-meter grid in EPSG:26917.")

    bounds = arcpy.Describe(pilot).extent
    rectangle = f"{bounds.XMin-200} {bounds.YMin-200} {bounds.XMax+200} {bounds.YMax+200}"
    work = root / "data/processed"
    work.mkdir(exist_ok=True)
    clipped = []
    for index, tile in enumerate(tiles, 1):
        target = str(work / f"dem_clip_{index}.tif")
        arcpy.management.Clip(str(tile), rectangle, target)
        clipped.append(target)

    dem = str(work / "snowpark_dem_1m.tif")
    arcpy.management.MosaicToNewRaster(clipped, str(work), Path(dem).name, crs,
                                       "32_BIT_FLOAT", 1, 1, "FIRST")
    arcpy.CheckOutExtension("Spatial")
    try:
        with arcpy.EnvManager(snapRaster=dem, cellSize=dem, extent=dem):
            slope = sa.Slope(dem, "DEGREE")
            aspect = sa.Aspect(dem)
            northness = sa.Con(aspect < 0, 0, sa.Cos(aspect * (3.141592653589793 / 180)))
            shade = sa.Hillshade(dem, 180, 25, "SHADOWS")
            for label, raster in (("elevation", arcpy.Raster(dem)), ("slope", slope),
                                  ("northness", northness), ("winter_noon_hillshade", shade)):
                table = str(gdb / f"SnowPark_{label}_stats")
                sa.ZonalStatisticsAsTable(pilot, "F_id", raster, table, "DATA", "ALL")
                actual = int(arcpy.management.GetCount(table)[0])
                print(f"{label}: {actual}/{count} zones", flush=True)
                if actual != count:
                    raise ValueError(f"Missing {label} statistics for some parking surfaces.")
    finally:
        arcpy.CheckInExtension("Spatial")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    run(parser.parse_args().root)
