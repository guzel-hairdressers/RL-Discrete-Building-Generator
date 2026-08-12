#!/usr/bin/env python3
"""
Custom Site Harvester — On-demand 3D urban context generator for custom global lat/lon coordinates.
Queries OpenStreetMap Overpass API, extrudes 3D buildings & road ribbons, and isolates custom site records.
"""

import os
import sys
import json
import math
import time
import argparse
import requests
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from geometry_3d import (
    latlon_to_local_meters,
    local_meters_to_latlon,
    compute_urban_metrics
)
from visualizer import create_3d_context_visualization, compute_area_tier
from harvest_all_osm import parse_osm_data

SITES_DIR = os.path.join(BASE_DIR, "app", "public", "sites")
CUSTOM_DS_PATH = os.path.join(BASE_DIR, "app", "public", "data", "custom_sites_dataset.json")


def fetch_custom_site(lat: float, lon: float, custom_name: str = "Custom Site"):
    """
    Harvest OpenStreetMap data for a custom (lat, lon) location, generate 3D WebGL scene,
    and save record in custom_sites_dataset.json.
    """
    os.makedirs(SITES_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(CUSTOM_DS_PATH), exist_ok=True)

    # Overpass API query (150m radius around lat, lon)
    overpass_url = "https://overpass-api.de/api/interpreter"
    query = f"""
    [out:json][timeout:25];
    (
      way["building"](around:150, {lat}, {lon});
      relation["building"](around:150, {lat}, {lon});
      way["highway"](around:150, {lat}, {lon});
    );
    out body;
    >;
    out skel qt;
    """

    headers = {'User-Agent': 'BuildingContextGenerator/1.0 (Thesis Research Project)'}
    print(f"[CustomHarvester] Fetching OSM data for Lat: {lat:.6f}, Lon: {lon:.6f}...")

    try:
        response = requests.post(overpass_url, data={'data': query}, headers=headers, timeout=30)
        response.raise_for_status()
        osm_data = response.json()
    except Exception as err:
        print(f"[CustomHarvester] Error querying Overpass API: {err}", file=sys.stderr)
        return None

    parsed_bldgs, parsed_roads = parse_osm_data(osm_data, lat, lon, default_h=18.0)

    if not parsed_bldgs:
        print("[CustomHarvester] Warning: No valid building footprints found at coordinates.", file=sys.stderr)
        return None

    # Find the building centroid closest to origin (0,0 local meters) as the target parcel
    site_b = min(parsed_bldgs, key=lambda b: math.hypot(b['centroid'][0], b['centroid'][1]))
    scx, scy = site_b['centroid'][0], site_b['centroid'][1]

    # Shift buildings relative to target site parcel centroid
    shifted_bldgs = []
    for b in parsed_bldgs:
        if b['id'] == site_b['id']:
            continue
        dist = math.hypot(b['centroid'][0] - scx, b['centroid'][1] - scy)
        if dist <= 100.0:  # 100m radius context box
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

    # Shift roads relative to target site parcel centroid
    shifted_roads = []
    for r in parsed_roads:
        shifted_pts = [[round(px - scx, 2), round(py - scy, 2)] for px, py in r['points_2d']]
        if any(math.hypot(px, py) <= 120.0 for px, py in shifted_pts):
            shifted_roads.append({
                'highway_type': r['highway_type'],
                'width_m': r['width_m'],
                'polyline_2d': shifted_pts,
                'points_2d': shifted_pts
            })

    site_verts = [[round(vx - scx, 2), round(vy - scy, 2)] for vx, vy in site_b['vertices_2d']]
    metrics = compute_urban_metrics(site_verts, shifted_bldgs, radius_m=100.0)
    area_tier = compute_area_tier(metrics['site_area_m2'])

    # Construct unique custom ID: custom_<tier>_<timestamp>
    timestamp = int(time.time())
    tier_code = area_tier.lower()
    site_id = f"custom_{tier_code}_{timestamp}"
    html_name = f"{site_id}.html"

    public_out_path = os.path.join(SITES_DIR, html_name)

    slat, slon = local_meters_to_latlon(scx, scy, lat, lon)

    scene_data = {
        'site_id': site_id,
        'city_code': 'custom',
        'city_name': custom_name,
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

    create_3d_context_visualization(scene_data, public_out_path)

    custom_record = {
        'site_id': site_id,
        'is_custom': True,
        'city_code': 'custom',
        'city_name': custom_name,
        'lat': round(slat, 6),
        'lon': round(slon, 6),
        'area_tier': area_tier,
        'site_area_m2': metrics['site_area_m2'],
        'avg_height_m': metrics['avg_height_m'],
        'max_height_m': metrics['max_height_m'],
        'building_count': len(shifted_bldgs),
        'far': metrics['floor_area_ratio'],
        'render_html': f"sites/{html_name}"
    }

    # Load or initialize custom_sites_dataset.json
    custom_dataset = []
    if os.path.exists(CUSTOM_DS_PATH):
        try:
            with open(CUSTOM_DS_PATH, 'r') as f:
                custom_dataset = json.load(f)
        except Exception:
            custom_dataset = []

    custom_dataset.insert(0, custom_record)

    with open(CUSTOM_DS_PATH, 'w') as f:
        json.dump(custom_dataset, f, indent=2)

    print(f"[CustomHarvester] Successfully generated custom 3D site: {site_id} ({area_tier} Tier, {metrics['site_area_m2']} m²)")
    return custom_record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Harvest custom OSM 3D site context")
    parser.add_argument("--lat", type=float, required=True, help="Latitude coordinate")
    parser.add_argument("--lon", type=float, required=True, help="Longitude coordinate")
    parser.add_argument("--name", type=str, default="Custom Site", help="Display name for location")
    args = parser.parse_args()

    res = fetch_custom_site(args.lat, args.lon, args.name)
    if res:
        print(json.dumps(res))
    else:
        sys.exit(1)
