import json
import math
import numpy as np

try:
    import osmnx as ox
    print("OSMnx version:", ox.__version__)

    LAT, LON = 40.7580, -73.9855
    DIST = 150.0  # meters

    print(f"Fetching features around ({LAT}, {LON}) via OSMnx...")

    # Fetch buildings
    try:
        bldgs = ox.features_from_point((LAT, LON), tags={'building': True}, dist=DIST)
    except AttributeError:
        bldgs = ox.geometries_from_point((LAT, LON), tags={'building': True}, dist=DIST)

    # Fetch roads
    try:
        roads = ox.features_from_point((LAT, LON), tags={'highway': True}, dist=DIST)
    except AttributeError:
        roads = ox.geometries_from_point((LAT, LON), tags={'highway': True}, dist=DIST)

    print(f"SUCCESS! Retrieved {len(bldgs)} building footprints and {len(roads)} road geometries via OSMnx!")

    # Save to GeoJSON
    bldgs.to_file("dataset/raw_nyc_bldgs.geojson", driver="GeoJSON")
    roads.to_file("dataset/raw_nyc_roads.geojson", driver="GeoJSON")
    print("Saved GeoJSON files to dataset/raw_nyc_bldgs.geojson and dataset/raw_nyc_roads.geojson!")

except Exception as e:
    print("OSMnx fetch failed:", e)
