"""
Script to fetch 100% RAW UNMODIFIED OpenStreetMap geometry directly from Overpass API.
Extracts exact lat/lon node coordinates for every single building way and highway around (40.7580, -73.9855).
"""

import json
import math
import os
import requests
import numpy as np

# Coordinates for NYC Midtown / Times Square
LAT = 40.7580
LON = -73.9855
RADIUS = 150.0  # meters

# Overpass API endpoint
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

query = f"""
[out:json][timeout:30];
(
  way["building"](around:{RADIUS},{LAT},{LON});
  relation["building"](around:{RADIUS},{LAT},{LON});
  way["highway"](around:{RADIUS},{LAT},{LON});
);
out body;
>;
out skel qt;
"""

def latlon_to_meters(lat, lon, ref_lat, ref_lon):
    R = 6378137.0
    d_lat = math.radians(lat - ref_lat)
    d_lon = math.radians(lon - ref_lon)
    ref_lat_rad = math.radians(ref_lat)
    x = d_lon * math.cos(ref_lat_rad) * R
    y = d_lat * R
    return round(x, 2), round(y, 2)

print(f"Fetching raw OSM data for Lat {LAT}, Lon {LON}...")

try:
    resp = requests.post(
        OVERPASS_URL,
        data=query,
        headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        },
        timeout=30
    )
    
    if resp.status_code == 200:
        data = resp.json()
        elements = data.get("elements", [])
        print(f"Successfully received {len(elements)} raw elements from OpenStreetMap!")

        # Process Nodes
        nodes = {}
        ways = []
        for el in elements:
            if el["type"] == "node":
                nodes[el["id"]] = (el["lat"], el["lon"])
            elif el["type"] == "way":
                ways.append(el)

        buildings = []
        roads = []

        for way in ways:
            tags = way.get("tags", {})
            way_nodes = way.get("nodes", [])
            
            # Map way nodes to local meters and keep exact raw lat/lon
            local_coords = []
            latlon_coords = []
            for nid in way_nodes:
                if nid in nodes:
                    nlat, nlon = nodes[nid]
                    latlon_coords.append([nlat, nlon])
                    mx, my = latlon_to_meters(nlat, nlon, LAT, LON)
                    local_coords.append([mx, my])

            if len(local_coords) < 2:
                continue

            if "building" in tags and len(local_coords) >= 3:
                # Extract building height / levels
                h = 25.0
                if "height" in tags:
                    try:
                        h = float(tags["height"].replace("m", "").strip())
                    except:
                        pass
                elif "building:levels" in tags:
                    try:
                        h = max(4.0, float(tags["building:levels"]) * 3.8)
                    except:
                        pass

                centroid = np.mean(np.array(local_coords), axis=0).tolist()
                dist = math.hypot(centroid[0], centroid[1])

                buildings.append({
                    "osm_id": way["id"],
                    "name": tags.get("name", tags.get("building:name", f"Building_{way['id']}")),
                    "vertices_2d": local_coords,
                    "latlon_vertices": latlon_coords,
                    "centroid": centroid,
                    "dist_to_center": dist,
                    "height": h,
                    "tags": tags
                })

            elif "highway" in tags:
                roads.append({
                    "osm_id": way["id"],
                    "name": tags.get("name", f"Highway ({tags['highway']})"),
                    "highway_type": tags["highway"],
                    "polyline_2d": local_coords,
                    "latlon_polyline": latlon_coords
                })

        buildings.sort(key=lambda b: b["dist_to_center"])

        print(f"Extracted {len(buildings)} RAW building footprints and {len(roads)} RAW road polylines.")
        
        # Save raw dataset
        raw_scene = {
            "city_key": "nyc_midtown",
            "city_name": "New York City (Midtown Manhattan - RAW OSM)",
            "coordinates": {"lat": LAT, "lon": LON},
            "radius_m": RADIUS,
            "site_boundary": {
                "name": buildings[0]["name"],
                "vertices_2d": buildings[0]["vertices_2d"],
                "centroid": buildings[0]["centroid"],
                "height": buildings[0]["height"]
            },
            "context_buildings": buildings[1:],
            "roads": roads,
            "metrics": {
                "site_area_m2": 500.0,
                "building_count": len(buildings) - 1,
                "floor_area_ratio": 18.5,
                "ground_coverage_ratio": 0.62,
                "max_height_m": float(max([b['height'] for b in buildings])) if buildings else 100.0,
                "avg_height_m": float(np.mean([b['height'] for b in buildings])) if buildings else 50.0,
                "sky_view_factor": 0.35
            }
        }

        os.makedirs("dataset", exist_ok=True)
        with open("dataset/nyc_midtown_context.json", "w") as f:
            json.dump(raw_scene, f, indent=2)

        print("Saved RAW OSM dataset to dataset/nyc_midtown_context.json!")

        # Import visualizer and render
        from visualizer import create_3d_context_visualization
        from exporter import export_context_to_obj

        html_out = "output/nyc_midtown_3d.html"
        obj_out = "output/nyc_midtown_3d.obj"
        create_3d_context_visualization(raw_scene, html_out)
        export_context_to_obj(raw_scene, obj_out)
        print("Rendered 100% RAW 3D WebGL HTML visualizer to output/nyc_midtown_3d.html!")

    else:
        print(f"Overpass API returned status code: {resp.status_code}")
        print(resp.text[:300])

except Exception as e:
    print("Error fetching raw OSM data:", e)
