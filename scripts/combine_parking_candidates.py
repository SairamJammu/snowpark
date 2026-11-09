"""Export the union of intersecting and nearby parking candidates by OSM ID."""

import argparse
import csv
from pathlib import Path

import arcpy


def run(root):
    gdb = root / "gis/snowpark/snowpark.gdb"
    source = str(gdb / "KSU_Parking_Working_UTM17N")
    baseline = str(gdb / "KSU_Parking_Intersect_Candidates")
    output = str(gdb / "KSU_Parking_Combined_Candidates")
    with arcpy.da.SearchCursor(baseline, ["F_id"]) as rows:
        intersecting = {osm_id for (osm_id,) in rows}
    report = root / "data/processed/parking_match_review.csv"
    with report.open(encoding="utf-8-sig", newline="") as handle:
        nearby = {row["osm_id"] for row in csv.DictReader(handle)
                  if row["review_status"] == "candidate_for_review"}
    ids = intersecting | nearby
    if not ids or not all(ids):
        raise ValueError("Candidate IDs must be populated.")
    field = arcpy.AddFieldDelimiters(source, "F_id")
    quoted = ", ".join("'" + osm_id.replace("'", "''") + "'" for osm_id in sorted(ids))
    where = f"{field} IN ({quoted})"
    with arcpy.da.SearchCursor(source, ["F_id"], where_clause=where) as rows:
        found = [osm_id for (osm_id,) in rows]
    if len(found) != len(ids) or set(found) != ids:
        raise ValueError("Candidate IDs must resolve to unique source features.")

    if not arcpy.Exists(output):
        arcpy.conversion.ExportFeatures(source, output, where)
    with arcpy.da.SearchCursor(output, ["F_id"]) as rows:
        existing = [osm_id for (osm_id,) in rows]
    if len(existing) != len(ids) or set(existing) != ids:
        raise ValueError("Existing combined layer differs from the computed candidate IDs.")
    print(f"{len(intersecting)} intersecting + {len(nearby - intersecting)} nearby = {len(ids)} candidates")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    run(parser.parse_args().root)
