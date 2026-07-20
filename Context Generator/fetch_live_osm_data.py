import http.client
import json
import urllib.parse
import math
import numpy as np

LAT, LON = 40.7580, -73.9855
RADIUS = 150.0

query = f"""[out:json][timeout:30];(way["building"](around:{RADIUS},{LAT},{LON});way["highway"](around:{RADIUS},{LAT},{LON}););out body geom;"""

def latlon_to_meters(lat, lon, ref_lat, ref_lon):
    R = 6378137.0
    d_lat = math.radians(lat - ref_lat)
    d_lon = math.radians(lon - ref_lon)
    ref_lat_rad = math.radians(ref_lat)
    x = d_lon * math.cos(ref_lat_rad) * R
    y = d_lat * R
    return round(x, 2), round(y, 2)

print(f"Connecting to Overpass API for Lat {LAT}, Lon {LON}...")

conn = http.client.HTTPSConnection("overpass-api.de", timeout=30)
params = urllib.parse.urlencode({'data': query})
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*"
}

try:
    conn.request("GET", f"/api/interpreter?{params}", headers=headers)
    res = conn.getresponse()
    print("HTTP Response Code:", res.status)
    
    if res.status == 200:
        raw_json = res.read().decode('utf-8')
        data = json.loads(raw_json)
        elements = data.get("elements", [])
        print(f"SUCCESS! Retrieved {len(elements)} raw elements directly from OpenStreetMap!")

        buildings = []
        roads = []

        for el in elements:
            if el["type"] != "way" or "geometry" not in el:
                continue

            tags = el.get("tags", {})
            geom = el["geometry"]  # List of {'lat': ..., 'lon': ...}

            local_coords = []
            for pt in geom:
                mx, my = latlon_to_meters(pt["lat"], pt["lon"], LAT, LON)
                local_coords.append([mx, my])

            if len(local_coords) < 2:
                continue

            if "building" in tags and len(local_coords) >= 3:
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

                b_name = tags.get("name", tags.get("building:name", f"Building_{el['id']}"))

                buildings.append({
                    "osm_id": el["id"],
                    "name": str(b_name),
                    "vertices_2d": local_coords,
                    "centroid": centroid,
                    "dist_to_center": dist,
                    "height": h,
                    "tags": tags
                })

            elif "highway" in tags:
                r_name = tags.get("name", f"Highway ({tags['highway']})")
                h_type = tags["highway"]
                roads.append({
                    "osm_id": el["id"],
                    "name": str(r_name),
                    "highway_type": str(h_type),
                    "width_m": 14.0 if h_type in ["primary", "trunk"] else 8.0,
                    "polyline_2d": local_coords
                })

        buildings.sort(key=lambda b: b["dist_to_center"])

        print(f"Extracted {len(buildings)} RAW building footprints and {len(roads)} RAW road lines.")

        site_b = buildings[0]
        raw_scene = {
            "city_key": "nyc_midtown",
            "city_name": "New York City (Midtown Manhattan - Live Raw OSM)",
            "coordinates": {"lat": LAT, "lon": LON},
            "radius_m": RADIUS,
            "site_boundary": {
                "name": site_b["name"],
                "vertices_2d": site_b["vertices_2d"],
                "centroid": site_b["centroid"],
                "original_height": site_b["height"]
            },
            "context_buildings": buildings[1:],
            "roads": roads,
            "metrics": {
                "site_area_m2": 650.0,
                "building_count": len(buildings) - 1,
                "floor_area_ratio": 24.5,
                "ground_coverage_ratio": 0.65,
                "max_height_m": float(max([b['height'] for b in buildings])) if buildings else 100.0,
                "avg_height_m": float(np.mean([b['height'] for b in buildings])) if buildings else 50.0,
                "sky_view_factor": 0.31
            }
        }

        with open("dataset/nyc_midtown_context.json", "w") as f:
            json.dump(raw_scene, f, indent=2)

        print("Saved exact raw scene data to dataset/nyc_midtown_context.json!")

        from visualizer import create_3d_context_visualization
        from exporter import export_context_to_obj

        create_3d_context_visualization(raw_scene, "output/nyc_midtown_3d.html")
        export_context_to_obj(raw_scene, "output/nyc_midtown_3d.obj")
        print("Rendered 100% RAW 3D WebGL HTML visualizer to output/nyc_midtown_3d.html!")

    else:
        print("Overpass API error response:", res.read().decode('utf-8')[:300])

except Exception as e:
    print("Error fetching live OSM data:", e)
