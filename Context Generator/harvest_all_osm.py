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
    'https://overpass-api.de/api/interpreter',
    'https://maps.mail.ru/osm/tools/overpass/api/interpreter'
]
HEADERS = {'User-Agent': 'BuildingContextGenerator/1.0 (academic research project; contact@thesis.edu)'}

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
            print(f"  [HTTP POST] Requesting buildings and roads from {server}...")
            resp = requests.post(server, data={'data': query}, headers=HEADERS, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if 'elements' in data and len(data['elements']) > 0:
                    return data
            else:
                print(f"  [HTTP {resp.status_code}] from {server}")
        except Exception as e:
            print(f"  [Server Error {server}]: {e}")
        time.sleep(1.0)
    return None

def parse_osm_data(data, ref_lat, ref_lon, default_h=35.0):
    if not data or 'elements' not in data:
        return [], []

    nodes = {e['id']: (e['lat'], e['lon']) for e in data['elements'] if e['type'] == 'node'}
    buildings = []
    roads = []

    for idx, elem in enumerate(data['elements']):
        if elem['type'] == 'way' and 'nodes' in elem:
            tags = elem.get('tags', {})

            # 1. Parse Building Footprints
            if 'building' in tags:
                coords = [nodes[nid] for nid in elem['nodes'] if nid in nodes]
                if len(coords) >= 3:
                    local_verts = []
                    for lat, lon in coords:
                        mx, my = latlon_to_local_meters(lat, lon, ref_lat, ref_lon)
                        local_verts.append([round(mx, 2), round(my, 2)])

                    if len(local_verts) >= 3:
                        try:
                            poly = Polygon(local_verts)
                            if poly.is_valid and poly.area >= 15.0:
                                area_m2 = poly.area
                                centroid = [poly.centroid.x, poly.centroid.y]

                                height = None
                                if 'height' in tags:
                                    try:
                                        val = str(tags['height']).replace('m', '').replace('ft', '').strip()
                                        height = float(val)
                                    except ValueError:
                                        pass

                                if height is None and 'building:levels' in tags:
                                    try:
                                        levels = float(tags['building:levels'])
                                        height = max(6.0, levels * 3.8)
                                    except ValueError:
                                        pass

                                if height is None:
                                    height = default_h

                                buildings.append({
                                    'id': f"osm_{elem['id']}",
                                    'name': tags.get('name', f"Building_{elem['id']}"),
                                    'vertices_2d': local_verts,
                                    'height': round(height, 1),
                                    'centroid': [round(centroid[0], 2), round(centroid[1], 2)],
                                    'area_m2': round(area_m2, 1),
                                    'tags': tags
                                })
                        except Exception:
                            pass

            # 2. Parse Road Network Polylines
            if 'highway' in tags:
                coords = [nodes[nid] for nid in elem['nodes'] if nid in nodes]
                if len(coords) >= 2:
                    local_pts = []
                    for lat, lon in coords:
                        mx, my = latlon_to_local_meters(lat, lon, ref_lat, ref_lon)
                        local_pts.append([round(mx, 2), round(my, 2)])

                    if len(local_pts) >= 2:
                        htype = tags.get('highway', 'residential')
                        width_m = 14.0 if htype in ['primary', 'trunk', 'motorway'] else (10.0 if htype in ['secondary', 'tertiary'] else 6.0)
                        roads.append({
                            'id': f"road_{elem['id']}",
                            'highway_type': htype,
                            'width_m': width_m,
                            'points_2d': local_pts
                        })

    return buildings, roads

def harvest_real_portfolio():
    print("=" * 70)
    print(" Harvesting 100% REAL OpenStreetMap 3D Urban Context Datasets with Road Networks")
    print("=" * 70)

    master_dataset = []
    global_id_counter = 1

    for city_key, info in TARGET_CITIES.items():
        city_code = info['city_code']
        ref_lat, ref_lon = info['lat'], info['lon']
        default_h = info.get('default_height', 35.0)

        print(f"\n[OSM Fetch] Querying real OSM buildings AND road network for {info['name']} ({city_code.upper()})...")
        osm_data = fetch_city_osm(ref_lat, ref_lon, dist_m=450)
        parsed_bldgs, parsed_roads = parse_osm_data(osm_data, ref_lat, ref_lon, default_h=default_h)

        if not parsed_bldgs:
            print(f"  [Warning] Could not parse building features for {city_key}.")
            continue

        print(f"  [Success] Parsed {len(parsed_bldgs)} real OSM building footprints and {len(parsed_roads)} road segments for {city_code.upper()}!")

        # Candidate site selection (sites with 150m² <= area <= 6000m²)
        candidate_sites = [b for b in parsed_bldgs if 150.0 <= b['area_m2'] <= 6000.0]
        np.random.seed(42 + global_id_counter)
        np.random.shuffle(candidate_sites)

        city_count = 0
        target_per_city = 65

        for site_b in candidate_sites:
            if city_count >= target_per_city:
                break

            scx, scy = site_b['centroid'][0], site_b['centroid'][1]

            # Shift coordinate origin to current site parcel centroid
            shifted_bldgs = []
            for b in parsed_bldgs:
                if b['id'] == site_b['id']:
                    continue
                dist = math.hypot(b['centroid'][0] - scx, b['centroid'][1] - scy)
                if dist <= 100.0:  # 100m radius context = 200m x 200m box
                    shifted_verts = [[round(vx - scx, 2), round(vy - scy, 2)] for vx, vy in b['vertices_2d']]
                    shifted_bldgs.append({
                        'id': b['id'],
                        'name': b['name'],
                        'vertices_2d': shifted_verts,
                        'height': b['height'],
                        'centroid': [round(b['centroid'][0] - scx, 2), round(b['centroid'][1] - scy, 2)],
                        'area_m2': b['area_m2'],
                        'tags': b.get('tags', {})
                    })

            if len(shifted_bldgs) < 3:
                continue

            # Shift roads relative to site parcel centroid
            shifted_roads = []
            for r in parsed_roads:
                shifted_pts = [[round(px - scx, 2), round(py - scy, 2)] for px, py in r['points_2d']]
                # Keep roads that cross or lie within 120m radius box
                if any(math.hypot(px, py) <= 120.0 for px, py in shifted_pts):
                    shifted_roads.append({
                        'highway_type': r['highway_type'],
                        'width_m': r['width_m'],
                        'points_2d': shifted_pts
                    })

            site_verts = [[round(vx - scx, 2), round(vy - scy, 2)] for vx, vy in site_b['vertices_2d']]
            metrics = compute_urban_metrics(site_verts, shifted_bldgs, radius_m=100.0)
            area_tier = compute_area_tier(metrics['site_area_m2'])

            num_str = f"{global_id_counter:04d}"
            tier_code = area_tier.lower()
            site_id = f"{tier_code}_{city_code}_{num_str}"
            html_name = f"{site_id}.html"

            out_path = os.path.join(OUTPUT_DIR, html_name)
            public_out_path = os.path.join(BASE_DIR, "app", "public", "output", html_name)

            scene_data = {
                'site_id': site_id,
                'city_code': city_code,
                'city_name': info['name'],
                'radius_m': 100.0,
                'site_boundary': {
                    'name': site_b['name'],
                    'vertices_2d': site_verts,
                    'centroid': [0.0, 0.0]
                },
                'context_buildings': shifted_bldgs,
                'roads': shifted_roads,
                'metrics': {
                    'site_area_m2': metrics['site_area_m2'],
                    'areaTier': area_tier,
                    'far': metrics['floor_area_ratio'],
                    'building_count': len(shifted_bldgs),
                    'max_height_m': metrics['max_height_m'],
                    'avg_height_m': metrics['avg_height_m']
                }
            }

            create_3d_context_visualization(scene_data, out_path)
            create_3d_context_visualization(scene_data, public_out_path)

            master_dataset.append({
                'site_id': site_id,
                'city_code': city_code,
                'city_name': info['name'],
                'area_tier': area_tier,
                'site_area_m2': metrics['site_area_m2'],
                'avg_height_m': metrics['avg_height_m'],
                'max_height_m': metrics['max_height_m'],
                'building_count': len(shifted_bldgs),
                'far': metrics['floor_area_ratio'],
                'render_html': f"output/{html_name}"
            })

            city_count += 1
            global_id_counter += 1

        time.sleep(2.0) # Pause between cities

    # Save Master Urban Dataset JSON
    master_path = os.path.join(DATASET_DIR, "master_urban_dataset.json")
    public_master_path = os.path.join(BASE_DIR, "app", "public", "dataset", "master_urban_dataset.json")

    with open(master_path, "w") as f:
        json.dump(master_dataset, f, indent=2)
    with open(public_master_path, "w") as f:
        json.dump(master_dataset, f, indent=2)

    print(f"\n[Complete] Successfully harvested {len(master_dataset)} 100% REAL OpenStreetMap urban context sites WITH ROAD NETWORKS!")

if __name__ == "__main__":
    harvest_real_portfolio()
