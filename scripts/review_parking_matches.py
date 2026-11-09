"""List nearby OSM polygons for campus markers that did not intersect a lot."""

import argparse
import csv
from pathlib import Path

import arcpy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("geodatabase", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--radius", type=float, default=15.0, help="Review radius in meters")
    args = parser.parse_args()
    if not 0 < args.radius < float("inf"):
        parser.error("--radius must be a positive finite distance")

    points = str(args.geodatabase / "KSU_Parking_Unmatched_Points")
    polygons = str(args.geodatabase / "KSU_Parking_Working_UTM17N")
    baseline = str(args.geodatabase / "KSU_Parking_Intersect_Candidates")
    for dataset in (points, polygons, baseline):
        if arcpy.Describe(dataset).spatialReference.factoryCode != 26917:
            parser.error(f"Expected NAD83 / UTM zone 17N (26917): {dataset}")

    with arcpy.da.SearchCursor(baseline, ["F_id"]) as cursor:
        intersecting_ids = {osm_id for (osm_id,) in cursor}
    with arcpy.da.SearchCursor(polygons, ["F_id", "SHAPE@"]) as cursor:
        outlines = [(osm_id, shape) for osm_id, shape in cursor if osm_id and shape]

    fields = ["concept3d_id", "name", "lot_key", "category"]
    rows = []
    nearby_count = 0
    with arcpy.da.SearchCursor(points, fields + ["SHAPE@"]) as cursor:
        for marker_id, name, lot_key, category, point in sorted(cursor, key=lambda row: str(row[0])):
            marker = (marker_id, name, lot_key, category)
            if point is None:
                rows.append((*marker, "missing_geometry", "", "", ""))
                continue
            candidates = sorted(
                (distance, osm_id)
                for osm_id, outline in outlines
                if 0 <= (distance := outline.distanceTo(point)) <= args.radius
            )
            if not candidates:
                rows.append((*marker, "no_outline_within_radius", "", "", ""))
                continue
            nearby_count += 1
            rows.extend(
                (*marker, "candidate_for_review", osm_id, f"{distance:.2f}", osm_id in intersecting_ids)
                for distance, osm_id in candidates
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8-sig") as output:
        writer = csv.writer(output)
        writer.writerow(fields + ["review_status", "osm_id", "distance_m", "in_intersection_export"])
        writer.writerows(rows)
    temporary.replace(args.output)
    print(f"{nearby_count} of {len({row[0] for row in rows})} markers have candidates within {args.radius:g} m")
    print(f"Wrote {len(rows)} review rows to {args.output}")


if __name__ == "__main__":
    main()
