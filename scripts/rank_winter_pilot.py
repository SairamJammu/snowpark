"""Model winter radiation and rank pilot surfaces by relative terrain exposure."""

import argparse
import csv
from pathlib import Path

import arcpy
import pandas as pd
from arcpy import sa


def run(root, reuse_solar=False):
    gdb = root / "gis/snowpark/snowpark.gdb"
    work = root / "data/processed"
    pilot = str(gdb / "SnowPark_Surface_Pilot")
    dem = str(work / "snowpark_dem_1m.tif")
    solar_dem = str(work / "snowpark_solar_dem_3m.tif")
    solar_raster = str(work / "snowpark_winter_solar_3m.tif")
    solar_table = str(gdb / "SnowPark_winter_solar_stats")
    arcpy.env.overwriteOutput = True
    arcpy.CheckOutExtension("Spatial")
    try:
        if not reuse_solar:
            arcpy.management.Resample(dem, solar_dem, "3", "BILINEAR")
            with arcpy.EnvManager(snapRaster=solar_dem, cellSize=solar_dem):
                radiation = sa.RasterSolarRadiation(
                    solar_dem, "12/1/2026 12:00:00 AM", "3/1/2027 12:00:00 AM",
                    in_analysis_mask=pilot, neighborhood_distance="150 Meters",
                    sunmap_grid_level=5,
                )
                radiation.save(solar_raster)
                sa.ZonalStatisticsAsTable(pilot, "F_id", solar_raster, solar_table, "DATA", "MEAN")
        with arcpy.da.SearchCursor(pilot, ["F_id"]) as rows:
            ids = {osm_id for (osm_id,) in rows}
        with arcpy.da.SearchCursor(solar_table, ["F_id", "MEAN"]) as rows:
            solar_values = {osm_id: value for osm_id, value in rows if value is not None}
        fallback_ids = ids - solar_values.keys()
        if fallback_ids:
            field = arcpy.AddFieldDelimiters(pilot, "F_id")
            quoted = ", ".join("'" + osm_id.replace("'", "''") + "'" for osm_id in sorted(fallback_ids))
            subset = str(gdb / "SnowPark_Solar_Fallback_Areas")
            arcpy.conversion.ExportFeatures(pilot, subset, f"{field} IN ({quoted})")
            bounds = arcpy.Describe(subset).extent
            rectangle = f"{bounds.XMin-200} {bounds.YMin-200} {bounds.XMax+200} {bounds.YMax+200}"
            local_dem = str(work / "snowpark_solar_fallback_dem_1m.tif")
            arcpy.management.Clip(dem, rectangle, local_dem)
            with arcpy.EnvManager(snapRaster=local_dem, cellSize=local_dem):
                finer = sa.RasterSolarRadiation(
                    local_dem, "12/1/2026 12:00:00 AM", "3/1/2027 12:00:00 AM",
                    in_analysis_mask=subset, neighborhood_distance="150 Meters",
                    sunmap_grid_level=5,
                )
                fallback = str(gdb / "SnowPark_winter_solar_fallback_stats")
                sa.ZonalStatisticsAsTable(subset, "F_id", finer, fallback, "DATA", "MEAN")
                with arcpy.da.SearchCursor(fallback, ["F_id", "MEAN"]) as rows:
                    solar_values.update({osm_id: value for osm_id, value in rows if value is not None})
        print(f"Solar coverage: {len(solar_values)}/{len(ids)}", flush=True)
    finally:
        arcpy.CheckInExtension("Spatial")

    with arcpy.da.SearchCursor(pilot, ["F_id", "name", "SHAPE@AREA"]) as rows:
        result = pd.DataFrame(rows, columns=["osm_id", "osm_name", "area_m2"])
    metrics = {
        "elevation": "elevation_m",
        "slope": "slope_deg",
        "northness": "northness",
        "winter_noon_hillshade": "noon_hillshade",

    }
    for table, column in metrics.items():
        with arcpy.da.SearchCursor(str(gdb / f"SnowPark_{table}_stats"), ["F_id", "MEAN"]) as rows:
            values = pd.DataFrame(rows, columns=["osm_id", column])
        result = result.merge(values, on="osm_id", how="left", validate="one_to_one")
    if result[list(metrics.values())].isna().any().any():
        raise ValueError("At least one pilot surface is missing a terrain statistic.")

    result["winter_solar_kwh_m2"] = result["osm_id"].map(solar_values)
    result["solar_grid_m"] = result["osm_id"].map(lambda osm_id: 1 if osm_id in fallback_ids else 3)
    complete = result["winter_solar_kwh_m2"].notna()
    result.loc[~complete, "solar_grid_m"] = None
    solar_rank = result.loc[complete, "winter_solar_kwh_m2"].rank(pct=True, ascending=False)
    shade_rank = result.loc[complete, "noon_hillshade"].rank(pct=True, ascending=False)
    north_rank = result.loc[complete, "northness"].rank(pct=True)
    result["pilot_score"] = 100 * (0.60 * solar_rank + 0.25 * shade_rank + 0.15 * north_rank)
    result["solar_only_score"] = 100 * solar_rank
    result["equal_weight_score"] = 100 * (solar_rank + shade_rank + north_rank) / 3
    result = result.sort_values(["pilot_score", "osm_id"], ascending=[False, True])
    destination = root / "outputs/tables/terrain_pilot.csv"
    destination.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(destination, index=False, float_format="%.4f", quoting=csv.QUOTE_MINIMAL)
    print(f"Wrote {len(result)} ranked surfaces to {destination}", flush=True)
    print(result[["pilot_score", "solar_only_score", "equal_weight_score"]].corr(method="spearman"), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--reuse-solar", action="store_true")
    args = parser.parse_args()
    run(args.root, args.reuse_solar)
