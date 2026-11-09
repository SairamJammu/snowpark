# SnowPark terrain pilot

SnowPark compares terrain conditions that may influence winter snow persistence across Kent State surface parking areas. The pilot uses 74 of the 81 candidate outlines. It requires the OSM tags for Kent State University as operator and surface parking, and holds out the White Hall building-shaped feature and any explicit review exclusions. Untagged and other parking types remain in the combined candidate layer for later review.

## Sources

- OpenStreetMap contributors, ODbL. The query is in scripts/download_parking.overpass. Use the November 5, 2026 GeoJSON export for this run.
- Kent State Concept3D map 568, extracted November 4, 2026. The reference layer contains 139 markers.
- USGS 3DEP Ohio Statewide Phase 1 (2019), 1-meter bare-earth elevations in meters relative to NAVD88. Download the two GeoTIFFs identified by x46y456 and x47y456 into data/raw/dem. Metadata: https://www.sciencebase.gov/catalog/item/64b61d89d34e70357a2b1311 and https://www.sciencebase.gov/catalog/item/64b61d83d34e70357a2b12fd.

## Run

Use the ArcGIS Pro Python environment with Spatial Analyst and pass the absolute SnowPark repository directory as the root argument.

1. Run scripts/review_parking_matches.py with the geodatabase path and data/processed/parking_match_review.csv as its output. The 15-meter radius screens for candidates.
2. Run scripts/combine_parking_candidates.py with the repository root to combine OSM IDs from the intersecting export and nearby review table. There are 71 intersecting outlines and 10 additional outlines.
3. Run scripts/build_terrain_pilot.py with the repository root. It creates a pilot feature class, prepares the DEM and computes per-surface terrain statistics.
4. Run scripts/rank_winter_pilot.py with the repository root. It models December through February radiation on a 3-meter grid, retries missing zones at 1 meter, and produces a percentile-based index plus two weighting comparisons.

The pilot index uses low solar radiation (60%), low winter-noon hillshade (25%), and north-facing terrain (15%). Elevation and slope are contextual metrics. The 2019 DEM models bare-earth terrain and may predate redevelopment. Building shadows, maintenance, plowing, salt and observed snow duration are outside the pilot. Validate the boundaries and compare with dated snow observations before treating the ranking as a field result.


5. Run scripts/map_terrain_pilot.py with the repository root to create a scored feature class and a local ArcGIS project. The map script expects SnowPark_Review.aprx beside the geodatabase.

## Pilot checks

- All 74 polygons have unique OSM IDs and positive area. No pair overlapped by more than one square meter.
- The four base terrain statistics cover 74 of 74 surfaces.
- The 3-meter solar run covered 72 surfaces. Two Stopher-area surfaces were processed at 1 meter. The results table records the grid used for each surface.
- Spearman rank correlations with the pilot index were 0.981 for solar-only and 0.985 for equal weights. These are sensitivity comparisons within the candidate set.
