"""Save a local ArcGIS map of the scored parking pilot."""

import argparse
import csv
from pathlib import Path

import arcpy


def run(root):
    folder = root / "gis/snowpark"
    gdb = folder / "snowpark.gdb"
    input_layer = str(gdb / "SnowPark_Surface_Pilot")
    output_layer = str(gdb / "SnowPark_Scored_Pilot")
    output_project = folder / "SnowPark_Terrain_Pilot.aprx"
    if arcpy.Exists(output_layer) or output_project.exists():
        raise FileExistsError("A scored feature class or project already exists.")
    with (root / "outputs/tables/terrain_pilot.csv").open(newline="", encoding="utf-8") as file:
        scores = {row["osm_id"]: row for row in csv.DictReader(file)}
    if not scores or any(not row["pilot_score"] for row in scores.values()):
        raise ValueError("Every pilot surface needs a score to build this map.")

    project = arcpy.mp.ArcGISProject(str(folder / "SnowPark_Review.aprx"))
    map_view = project.listMaps()[0]
    arcpy.management.CopyFeatures(input_layer, output_layer)
    attributes = ["pilot_score", "winter_solar_kwh_m2", "slope_deg", "solar_grid_m"]
    for attribute in attributes:
        arcpy.management.AddField(output_layer, attribute, "DOUBLE")
    with arcpy.da.UpdateCursor(output_layer, ["F_id"] + attributes) as cursor:
        for row in cursor:
            cursor.updateRow([row[0], *[float(scores[row[0]][key]) for key in attributes]])

    for layer in map_view.listLayers():
        if layer.isFeatureLayer and not layer.isBroken:
            if Path(layer.dataSource).name.startswith(("KSU_", "OSM_")):
                layer.visible = False
    layer = map_view.addDataFromPath(output_layer)
    layer.name = "SnowPark pilot score"
    symbology = layer.symbology
    symbology.updateRenderer("GraduatedColorsRenderer")
    renderer = symbology.renderer
    renderer.classificationField = "pilot_score"
    renderer.classificationMethod = "EqualInterval"
    renderer.breakCount = 5
    ramps = project.listColorRamps("Yellow-Orange-Red*")
    if ramps:
        renderer.colorRamp = ramps[0]
    layer.symbology = symbology
    map_view.defaultCamera.setExtent(arcpy.Describe(output_layer).extent)
    project.saveACopy(str(output_project))
    check = arcpy.mp.ArcGISProject(str(output_project))
    saved_layer = check.listMaps()[0].listLayers("SnowPark pilot score")[0]
    if saved_layer.isBroken or int(arcpy.management.GetCount(output_layer)[0]) != len(scores):
        raise RuntimeError("The saved score layer did not pass verification.")
    print(f"Verified {len(scores)} scored features in {output_project}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    run(parser.parse_args().root)
