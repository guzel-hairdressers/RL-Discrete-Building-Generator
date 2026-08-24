import os
import sys
import json
import time
import math
import requests
import numpy as np
from shapely.geometry import Polygon, MultiPolygon

from config import TARGET_CITIES, DATASET_DIR, OUTPUT_DIR, BASE_DIR
from geometry_3d import latlon_to_local_meters, compute_urban_metrics
from visualizer import create_3d_context_visualization, compute_area_tier

OVERPASS_SERVERS = [
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass-api.de/api/interpreter',
    'https://maps.mail.ru/osm/tools/overpass/api/interpreter'
]
HEADERS = {
    'User-Agent': 'BuildingContextGenerator/1.0 (academic research project; contact@thesis.edu)',
    'Content-Type': 'application/x-www-form-urlencoded'
}

def fetch_city_osm(lat, lon, dist_m=450):
    query = f"""
    [out:json][timeout:30];
    (
      way["building"](around:{dist_m},{lat},{lon});
      way["highway"](around:{dist_m},{lat},{lon});
    );
    out body;
    >;
    out skel qt;
    """
    for server in OVERPASS_SERVERS:
        try:
            print(f"  [Fetcher] Querying Overpass server: {server}...")
            res = requests.post(server, data={'data': query}, headers=HEADERS, timeout=(5, 10))
            if res.status_code == 200:
                data = res.json()
                if "elements" in data and len(data["elements"]) > 0:
                    return data
        except Exception as e:
            print(f"  [Fetcher] Mirror {server} error: {e}")
            time.sleep(1)
    return None

def parse_osm_data(osm_json, center_lat, center_lon, default_h=18.0):
    elements = osm_json.get("elements", [])
    nodes = {}
    for el in elements:
        if el["type"] == "node":
            nodes[el["id"]] = (el["lat"], el["lon"])

    bldgs = []
    roads = []

    for el in elements:
        if el["type"] == "way":
            tags = el.get("tags", {})
            w_nodes = el.get("nodes", [])

            # Parse buildings
            if "building" in tags:
                if len(w_nodes) < 3:
                    continue
                coords_local = []
                for nid in w_nodes:
                    if nid in nodes:
                        nlat, nlon = nodes[nid]
                        lx, ly = latlon_to_local_meters(nlat, nlon, center_lat, center_lon)
                        coords_local.append([lx, ly])

                if len(coords_local) >= 3:
                    if coords_local[0] == coords_local[-1]:
                        coords_local.pop()

                    if len(coords_local) >= 3:
                        poly = Polygon(coords_local)
                        if not poly.is_valid:
                            poly = poly.buffer(0)

                        if poly.geom_type == 'Polygon' and poly.area > 15.0:
                            h = default_h
                            if "height" in tags:
                                try:
                                    h = float(tags["height"].replace("m", "").strip())
                                except:
                                    pass
                            elif "building:levels" in tags:
                                try:
                                    h = float(tags["building:levels"]) * 3.5
                                except:
                                    pass

                            bldgs.append({
                                'id': f"bldg_{el['id']}",
                                'vertices': list(poly.exterior.coords)[:-1],
                                'faces': list(range(len(poly.exterior.coords) - 1)),
                                'area': poly.area,
                                'centroid': [poly.centroid.x, poly.centroid.y],
                                'height_m': h
                            })

            # Parse roads
            elif "highway" in tags:
                if len(w_nodes) < 2:
                    continue
                coords_local = []
                for nid in w_nodes:
                    if nid in nodes:
                        nlat, nlon = nodes[nid]
                        lx, ly = latlon_to_local_meters(nlat, nlon, center_lat, center_lon)
                        coords_local.append([lx, ly])

                if len(coords_local) >= 2:
                    hw_type = tags.get("highway", "road")
                    w_m = 6.0
                    if hw_type in ['primary', 'trunk', 'motorway']:
                        w_m = 10.0
                    elif hw_type in ['secondary', 'tertiary']:
                        w_m = 8.0
                    elif hw_type in ['residential', 'unclassified', 'service']:
                        w_m = 5.0

                    roads.append({
                        'highway_type': hw_type,
                        'width_m': w_m,
                        'polyline_2d': coords_local
                    })

    return bldgs, roads

def fetch_real_portfolio():
    print("=== Fetching Real OpenStreetMap 3D Urban Context Sites ===")
    os.makedirs(DATASET_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    master_dataset = []
    site_counter = 1

    for ccode, cinfo in TARGET_CITIES.items():
        cname = cinfo["name"]
        clat = cinfo["lat"]
        clon = cinfo["lon"]
        def_h = cinfo.get("avg_h", 18.0)

        print(f"\nFetching city: {cname} ({ccode.toUpperCase() if hasattr(ccode, 'toUpperCase') else ccode.upper()}) at Lat: {clat}, Lon: {clon}...")
        osm_json = fetch_city_osm(clat, clon, dist_m=600)

        if not osm_json:
            print(f"  [Error] Failed to fetch OSM data for {cname}")
            continue

        bldgs, roads = parse_osm_data(osm_json, clat, clon, default_h=def_h)
        print(f"  Found {len(bldgs)} building footprints and {len(roads)} road segments.")

        if len(bldgs) < 5:
            continue

        bldgs.sort(key=lambda b: b['area'], reverse=True)
        sample_size = min(15, len(bldgs))
        selected_targets = bldgs[:sample_size]

        for target_b in selected_targets:
            scx, scy = target_b['centroid'][0], target_b['centroid'][1]

            shifted_bldgs = []
            for b in bldgs:
                if b['id'] == target_b['id']:
                    continue
                dist = math.hypot(b['centroid'][0] - scx, b['centroid'][1] - scy)
                if dist <= 120.0:
                    shifted_bldgs.append({
                        'id': b['id'],
                        'vertices': [[round(v[0] - scx, 2), round(v[1] - scy, 2)] for v in b['vertices']],
                        'faces': b['faces'],
                        'area': b['area'],
                        'height_m': b['height_m']
                    })

            if len(shifted_bldgs) < 2:
                continue

            shifted_site_verts = [[round(v[0] - scx, 2), round(v[1] - scy, 2)] for v in target_b['vertices']]

            shifted_roads = []
            for r in roads:
                pts = r['polyline_2d']
                shifted_pts = [[round(pt[0] - scx, 2), round(pt[1] - scy, 2)] for pt in pts]
                shifted_roads.append({
                    'highway_type': r['highway_type'],
                    'width_m': r['width_m'],
                    'polyline_2d': shifted_pts
                })

            site_area_m2 = target_b['area']
            area_tier = compute_area_tier(site_area_m2)
            site_id = f"{area_tier.lower()}_{ccode}_{site_counter:04d}"

            metrics = compute_urban_metrics(shifted_site_verts, shifted_bldgs)

            scene_data = {
                'siteId': site_id,
                'cityName': cname,
                'coords': {'lat': clat, 'lon': clon},
                'siteArea': round(metrics['site_area_m2'], 2),
                'areaTier': area_tier,
                'metrics': metrics,
                'sitePerimeter': shifted_site_verts,
                'buildings': shifted_bldgs,
                'roads': shifted_roads,
                'maxHeight': max([b['height_m'] for b in shifted_bldgs] + [def_h])
            }

            html_name = f"{site_id}.html"
            public_out_path = os.path.join(OUTPUT_DIR, html_name)

            create_3d_context_visualization(scene_data, public_out_path)

            record = {
                'site_id': site_id,
                'city_code': ccode,
                'city_name': cname,
                'area_tier': area_tier,
                'site_area_m2': metrics['site_area_m2'],
                'avg_height_m': metrics['avg_height_m'],
                'max_height_m': metrics['max_height_m'],
                'building_count': len(shifted_bldgs),
                'far': metrics['floor_area_ratio'],
                'render_html': f"sites/{html_name}",
                'lat': clat,
                'lon': clon
            }

            master_dataset.append(record)
            site_counter += 1

    master_path = os.path.join(DATASET_DIR, "master_urban_dataset.json")
    with open(master_path, 'w') as f:
        json.dump(master_dataset, f, indent=2)

    print(f"\n[Complete] Successfully fetched {len(master_dataset)} 100% REAL OpenStreetMap urban context sites WITH ROAD NETWORKS!")
    print(f"Master dataset saved to: {master_path}")

if __name__ == "__main__":
    fetch_real_portfolio()
