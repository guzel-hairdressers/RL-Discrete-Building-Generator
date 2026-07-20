"""
OSM Urban Context Extractor module.
Extracts genuine 3D building geometries and real street networks (Broadway, 7th Ave, W 45th St, etc.)
for real-world city targets (NYC Midtown, Tokyo Shinjuku, Barcelona, London).
"""

import json
import math
import os
import urllib.request
import urllib.parse
import numpy as np

from config import TARGET_CITIES, DATASET_DIR, DEFAULT_RADIUS
from geometry_3d import latlon_to_local_meters, extrude_polygon_to_3d_mesh, compute_urban_metrics

# Public Overpass API Mirrors
OVERPASS_ENDPOINTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

ROAD_WIDTHS = {
    "motorway": 20.0,
    "trunk": 18.0,
    "primary": 14.0,
    "secondary": 10.0,
    "tertiary": 8.0,
    "residential": 6.5,
    "unclassified": 6.0,
    "service": 4.5,
    "pedestrian": 8.0,
    "footway": 3.0,
}


def fetch_osm_overpass_data(lat, lon, radius=100.0):
    """
    Attempts live query from Overpass API.
    """
    query = f"""
    [out:json][timeout:25];
    (
      way["building"](around:{radius},{lat},{lon});
      relation["building"](around:{radius},{lat},{lon});
      way["highway"](around:{radius},{lat},{lon});
    );
    out body;
    >;
    out skel qt;
    """

    encoded_data = urllib.parse.urlencode({'data': query}).encode('utf-8')
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/javascript, */*; q=0.01'
    }

    for endpoint in OVERPASS_ENDPOINTS:
        try:
            req = urllib.request.Request(endpoint, data=encoded_data, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    parsed = parse_overpass_buildings_and_roads(data, lat, lon)
                    if parsed and len(parsed["buildings"]) > 0:
                        print(f"[OSM Extractor] Successfully fetched live OSM geometry from: {endpoint}")
                        return parsed
        except Exception:
            pass

    return None


def parse_overpass_buildings_and_roads(data, ref_lat, ref_lon):
    elements = data.get("elements", [])
    nodes = {}
    building_ways = []
    highway_ways = []

    for el in elements:
        if el["type"] == "node":
            nodes[el["id"]] = (el["lat"], el["lon"])
        elif el["type"] == "way" and "tags" in el:
            tags = el["tags"]
            if "building" in tags:
                building_ways.append(el)
            elif "highway" in tags:
                highway_ways.append(el)

    parsed_buildings = []
    for way in building_ways:
        way_nodes = way.get("nodes", [])
        if len(way_nodes) < 3:
            continue

        local_coords = []
        for nid in way_nodes:
            if nid in nodes:
                nlat, nlon = nodes[nid]
                x, y = latlon_to_local_meters(nlat, nlon, ref_lat, ref_lon)
                local_coords.append([round(x, 2), round(y, 2)])

        if len(local_coords) < 3:
            continue

        tags = way.get("tags", {})
        height = extract_height_from_tags(tags)
        b_name = tags.get("name", tags.get("building:name", f"Building {way['id']}"))

        coords_arr = np.array(local_coords)
        centroid = np.mean(coords_arr, axis=0).tolist()
        dist_to_center = math.hypot(centroid[0], centroid[1])

        parsed_buildings.append({
            "id": way["id"],
            "name": b_name,
            "vertices_2d": local_coords,
            "centroid": centroid,
            "dist_to_center": dist_to_center,
            "height": height,
            "tags": tags
        })

    parsed_roads = []
    for way in highway_ways:
        way_nodes = way.get("nodes", [])
        if len(way_nodes) < 2:
            continue

        road_coords = []
        for nid in way_nodes:
            if nid in nodes:
                nlat, nlon = nodes[nid]
                x, y = latlon_to_local_meters(nlat, nlon, ref_lat, ref_lon)
                road_coords.append([round(x, 2), round(y, 2)])

        if len(road_coords) < 2:
            continue

        tags = way.get("tags", {})
        h_type = tags.get("highway", "residential")
        r_name = tags.get("name", f"Road ({h_type})")
        r_width = ROAD_WIDTHS.get(h_type, 7.0)

        parsed_roads.append({
            "id": way["id"],
            "name": r_name,
            "highway_type": h_type,
            "width_m": r_width,
            "polyline_2d": road_coords
        })

    return {
        "buildings": parsed_buildings,
        "roads": parsed_roads
    }


def extract_height_from_tags(tags, default_height=28.0):
    if "height" in tags:
        try:
            val = tags["height"].replace("m", "").strip()
            return float(val)
        except ValueError:
            pass
    if "building:height" in tags:
        try:
            val = tags["building:height"].replace("m", "").strip()
            return float(val)
        except ValueError:
            pass
    if "building:levels" in tags:
        try:
            levels = float(tags["building:levels"])
            return max(4.0, levels * 3.8)
        except ValueError:
            pass

    return default_height


def extract_city_context(city_key, radius=100.0):
    if city_key not in TARGET_CITIES:
        raise ValueError(f"Unknown city key '{city_key}'. Available: {list(TARGET_CITIES.keys())}")

    info = TARGET_CITIES[city_key]
    ref_lat, ref_lon = info["lat"], info["lon"]

    print(f"\n[OSM Extractor] Extracting real urban context for {info['name']}...")
    print(f"  - Target Coordinates: Lat {ref_lat}, Lon {ref_lon}")

    # Check if pre-cached real dataset exists
    cached_dataset_file = os.path.join(DATASET_DIR, f"{city_key}_context.json")
    if os.path.exists(cached_dataset_file):
        with open(cached_dataset_file, "r") as f:
            context_scene = json.load(f)
        print(f"[OSM Extractor] Loaded real OSM footprint & road dataset from: {cached_dataset_file}")
        return context_scene

    # Try live query
    osm_data = fetch_osm_overpass_data(ref_lat, ref_lon, radius=radius)
    if not osm_data or not osm_data["buildings"]:
        raise RuntimeError(f"Could not reach live Overpass API for '{city_key}'. Pre-cached dataset available in dataset/{city_key}_context.json.")

    raw_buildings = osm_data["buildings"]
    raw_roads = osm_data["roads"]
    raw_buildings.sort(key=lambda b: b["dist_to_center"])

    site_building = raw_buildings[0]
    site_boundary_verts = site_building["vertices_2d"]

    context_buildings = []
    for b in raw_buildings[1:]:
        mesh_3d = extrude_polygon_to_3d_mesh(b["vertices_2d"], b["height"])
        if mesh_3d:
            context_buildings.append({
                "id": f"bldg_{b['id']}",
                "name": b["name"],
                "vertices_2d": b["vertices_2d"],
                "height": b["height"],
                "mesh_3d": mesh_3d,
                "centroid": b["centroid"]
            })

    metrics = compute_urban_metrics(site_boundary_verts, context_buildings)

    context_scene = {
        "city_key": city_key,
        "city_name": info["name"],
        "typology": info["typology"],
        "density_class": info["density_class"],
        "coordinates": {"lat": ref_lat, "lon": ref_lon},
        "verification_links": {
            "google_maps": f"https://www.google.com/maps?q={ref_lat},{ref_lon}",
            "openstreetmap": f"https://www.openstreetmap.org/#map=18/{ref_lat}/{ref_lon}"
        },
        "radius_m": radius,
        "site_boundary": {
            "name": site_building["name"],
            "vertices_2d": site_boundary_verts,
            "centroid": site_building["centroid"],
            "original_height": site_building["height"]
        },
        "context_buildings": context_buildings,
        "roads": raw_roads,
        "metrics": metrics
    }

    with open(cached_dataset_file, "w") as f:
        json.dump(context_scene, f, indent=2)

    return context_scene
