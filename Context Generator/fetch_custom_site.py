#!/usr/bin/env python3
"""
Custom Site Fetcher — On-demand 3D urban context generator for custom global lat/lon coordinates.
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

from shapely.geometry import Polygon, LineString
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from geometry_3d import (
    latlon_to_local_meters,
    local_meters_to_latlon,
    compute_urban_metrics
)
from visualizer import create_3d_context_visualization, compute_area_tier
from fetch_all_osm import parse_osm_data

SITES_DIR = os.path.join(BASE_DIR, "app", "public", "sites")
CUSTOM_DS_PATH = os.path.join(BASE_DIR, "app", "public", "data", "custom_sites_dataset.json")


def compute_smart_parcel(site_b_verts, shifted_bldgs, shifted_roads, custom_polygon=None, road_setback=2.0, building_setback=3.0, parcel_type="convex_hull"):
    """
    Computes realistic urban land parcel boundary and returns debug layers:
    1. Base Parcel Geometry: Convex Hull
    2. Setback Expansion (yard buffer)
    3. Road Clipping with curb setback
    4. Subtract neighbor building footprints
    5. Footprint Conservation Union so parcel NEVER shrinks inside original building footprint
    """
    debug_layers = {}
    try:
        from shapely.geometry import Polygon, LineString
        from shapely.geometry.polygon import orient
        from shapely.ops import unary_union

        b_poly = Polygon(site_b_verts)
        if not b_poly.is_valid:
            b_poly = b_poly.buffer(0)

        # 1. Base Geometry: Convex Hull
        ch_poly = b_poly.convex_hull
        ch_coords = list(ch_poly.exterior.coords)
        if ch_coords[0] == ch_coords[-1]: ch_coords.pop()
        debug_layers['convex_hull'] = [[round(pt[0], 2), round(pt[1], 2)] for pt in ch_coords]

        # 2. Setback Expansion (yard buffer around convex hull with sharp mitre corners)
        exp_poly = ch_poly.buffer(float(building_setback), join_style='mitre', mitre_limit=10.0)
        exp_coords = list(exp_poly.exterior.coords)
        if exp_coords[0] == exp_coords[-1]: exp_coords.pop()
        debug_layers['setback_buffer'] = [[round(pt[0], 2), round(pt[1], 2)] for pt in exp_coords]

        # 3. Road Clipping with curb setback (FILTER ONLY VEHICULAR ROADS, USE ROUND FILLETS)
        EXCLUDED_ROADS = {'footway', 'path', 'steps', 'cycleway', 'track', 'bridleway', 'pedestrian', 'footpath'}
        road_polys = []
        road_lines = []
        for r in shifted_roads:
            hw_type = str(r.get('highway_type', 'road')).lower()
            if hw_type in EXCLUDED_ROADS:
                continue

            pts = r.get('polyline_2d', [])
            w = r.get('width_m', 6.0)
            if len(pts) >= 2:
                try:
                    line = LineString(pts)
                    r_road = line.buffer(w / 2.0, cap_style='round', join_style='round')
                    r_curb = r_road.buffer(float(road_setback), cap_style='round', join_style='round')
                    if r_curb.is_valid and not r_curb.is_empty:
                        road_polys.append(r_curb)

                    # Extract dual-side parallel offset curves (left and right) for crystal clear 3D line rendering
                    d_curb = w / 2.0 + float(road_setback)
                    for side in ['left', 'right']:
                        try:
                            off_l = line.parallel_offset(d_curb, side)
                            if not off_l.is_empty:
                                if off_l.geom_type == 'LineString':
                                    l_pts = list(off_l.coords)
                                    road_lines.append([[round(pt[0], 2), round(pt[1], 2)] for pt in l_pts])
                                elif off_l.geom_type == 'MultiLineString':
                                    for sub_l in off_l.geoms:
                                        l_pts = list(sub_l.coords)
                                        road_lines.append([[round(pt[0], 2), round(pt[1], 2)] for pt in l_pts])
                        except Exception:
                            pass
                except Exception:
                    pass

        road_setbacks = []
        if road_polys:
            union_roads = unary_union(road_polys)
            if union_roads.geom_type == 'Polygon':
                u_polys = [union_roads]
            elif union_roads.geom_type == 'MultiPolygon':
                u_polys = list(union_roads.geoms)
            else:
                u_polys = []

            for u_p in u_polys:
                if u_p.is_valid and u_p.area > 1.0:
                    r_coords = list(u_p.exterior.coords)
                    if r_coords[0] == r_coords[-1]: r_coords.pop()
                    road_setbacks.append([[round(pt[0], 2), round(pt[1], 2)] for pt in r_coords])
                    exp_poly = exp_poly.difference(u_p)

        debug_layers['road_setbacks'] = road_lines if road_lines else road_setbacks

        if custom_polygon and len(custom_polygon) >= 3:
            p = Polygon(custom_polygon)
            if not p.is_valid:
                p = p.buffer(0)
            p = orient(p, sign=1.0)
            if p.is_valid and p.area > 1.0:
                coords = list(p.exterior.coords)
                if coords[0] == coords[-1]:
                    coords.pop()
                return [[round(pt[0], 2), round(pt[1], 2)] for pt in coords], debug_layers

        # 4. Subtract neighbor building footprints
        for neighbor in shifted_bldgs:
            n_verts = neighbor.get('vertices', neighbor.get('vertices_2d', []))
            if len(n_verts) >= 3:
                try:
                    n_poly = Polygon(n_verts)
                    if not n_poly.is_valid:
                        n_poly = n_poly.buffer(0)
                    if n_poly.area > 0 and exp_poly.intersects(n_poly):
                        exp_poly = exp_poly.difference(n_poly)
                except Exception:
                    pass

        # 5. Union with target building footprint at the very end
        exp_poly = exp_poly.union(b_poly)

        if exp_poly.geom_type == 'MultiPolygon':
            exp_poly = max(exp_poly.geoms, key=lambda g: g.area)

        coords = list(exp_poly.exterior.coords)
        if coords[0] == coords[-1]:
            coords.pop()
        return [[round(pt[0], 2), round(pt[1], 2)] for pt in coords], debug_layers
    except Exception as e:
        print(f"[CustomFetcher] Smart parcel computation failed: {e}", file=sys.stderr)
        return site_b_verts, debug_layers


def fetch_custom_site(lat: float, lon: float, custom_name: str = "Custom Site", custom_polygon: list = None, road_setback: float = 2.0, building_setback: float = 3.0, parcel_type: str = "convex_hull"):
    """
    Fetch OpenStreetMap data for a custom (lat, lon) location, generate 3D WebGL scene,
    and save record in custom_sites_dataset.json.
    """
    os.makedirs(SITES_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(CUSTOM_DS_PATH), exist_ok=True)

    # Clean custom_name (strip any appended custom tags or non-Latin clutter)
    custom_name = custom_name.replace('(Custom)', '').replace('(custom)', '').replace('(Custom Site)', '').strip()
    if not custom_name:
        custom_name = "Custom Location"

    OVERPASS_SERVERS = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass.nchc.org.tw/api/interpreter",
        "https://overpass.private.coffee/api/interpreter",
        "https://overpass.osm.ch/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
    ]

    query = f"""
    [out:json][timeout:15];
    (
      way["building"](around:140, {lat}, {lon});
      relation["building"](around:140, {lat}, {lon});
      way["highway"](around:140, {lat}, {lon});
    );
    out body;
    >;
    out skel qt;
    """

    headers = {
        'User-Agent': 'BuildingContextGenerator/1.0 (Thesis Research Project)',
        'Accept-Language': 'en-US,en;q=0.9',
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _query_mirror(server_url):
        try:
            resp = requests.post(server_url, data={'data': query}, headers={'User-Agent': 'BuildingContextGenerator/1.0', 'Accept-Language': 'en-US,en;q=0.9'}, timeout=(3, 10))
            if resp.status_code == 200:
                data = resp.json()
                if "elements" in data and len(data["elements"]) > 0:
                    return data
        except Exception:
            pass
        try:
            resp = requests.get(server_url, params={'data': query}, headers={'User-Agent': 'BuildingContextGenerator/1.0', 'Accept-Language': 'en-US,en;q=0.9'}, timeout=(3, 10))
            if resp.status_code == 200:
                data = resp.json()
                if "elements" in data and len(data["elements"]) > 0:
                    return data
        except Exception:
            pass
        return None

    osm_data = None
    print(f"[CustomFetcher] Querying {len(OVERPASS_SERVERS)} Overpass mirrors in parallel...")
    with ThreadPoolExecutor(max_workers=len(OVERPASS_SERVERS)) as executor:
        futures = [executor.submit(_query_mirror, url) for url in OVERPASS_SERVERS]
        for future in as_completed(futures):
            res_data = future.result()
            if res_data is not None:
                osm_data = res_data
                break

    if not osm_data:
        print("[CustomFetcher] Error: All Overpass API servers timed out or failed.", file=sys.stderr)
        return None

    parsed_bldgs, parsed_roads = parse_osm_data(osm_data, lat, lon, default_h=18.0)

    if not parsed_bldgs:
        print("[CustomFetcher] Warning: No valid building footprints found at coordinates.", file=sys.stderr)
        return None

    # Determine central site parcel origin (scx, scy) and drawn polygon geometry
    shifted_custom_polygon = None
    if custom_polygon and len(custom_polygon) >= 3:
        raw_custom_pts = [latlon_to_local_meters(pt[0], pt[1], lat, lon) for pt in custom_polygon]
        c_poly = Polygon(raw_custom_pts)
        if not c_poly.is_valid:
            c_poly = c_poly.buffer(0)
        scx, scy = c_poly.centroid.x, c_poly.centroid.y
        shifted_custom_polygon = [[round(p[0] - scx, 2), round(p[1] - scy, 2)] for p in raw_custom_pts]
        site_area_m2 = round(c_poly.area, 2)
        site_b_id = None
    else:
        site_b = min(parsed_bldgs, key=lambda b: math.hypot(b['centroid'][0], b['centroid'][1]))
        scx, scy = site_b['centroid'][0], site_b['centroid'][1]
        site_area_m2 = site_b['area']
        site_b_id = site_b['id']

    custom_shapely_poly = Polygon(shifted_custom_polygon) if shifted_custom_polygon else None
    if custom_shapely_poly and not custom_shapely_poly.is_valid:
        custom_shapely_poly = custom_shapely_poly.buffer(0)

    # Shift buildings relative to target site parcel centroid
    shifted_bldgs = []
    for b in parsed_bldgs:
        if site_b_id and b['id'] == site_b_id:
            continue
        dist = math.hypot(b['centroid'][0] - scx, b['centroid'][1] - scy)
        if dist <= 100.0:  # 100m radius context box
            v_list = [[round(v[0] - scx, 2), round(v[1] - scy, 2)] for v in b['vertices']]
            if custom_shapely_poly and len(v_list) >= 3:
                try:
                    b_poly = Polygon(v_list)
                    if not b_poly.is_valid:
                        b_poly = b_poly.buffer(0)
                    if custom_shapely_poly.intersects(b_poly):
                        # Discard building completely if it intersects drawn site parcel
                        continue
                except Exception:
                    pass

            shifted_bldgs.append({
                'id': b['id'],
                'vertices': v_list,
                'vertices_2d': v_list,
                'faces': b['faces'],
                'area': b['area'],
                'height_m': b['height_m']
            })

    raw_site_verts = shifted_custom_polygon if shifted_custom_polygon else [[round(v[0] - scx, 2), round(v[1] - scy, 2)] for v in site_b['vertices']]

    # Shift roads relative to target site parcel centroid
    shifted_roads = []
    for r in parsed_roads:
        pts = r.get('polyline_2d', [])
        shifted_pts = [[round(pt[0] - scx, 2), round(pt[1] - scy, 2)] for pt in pts]
        shifted_roads.append({
            'highway_type': r.get('highway_type', 'road'),
            'width_m': r.get('width_m', 6.0),
            'polyline_2d': shifted_pts
        })

    # Compute smart parcel boundary (road/neighbor clipping, footprint union)
    shifted_site_verts, debug_layers = compute_smart_parcel(raw_site_verts, shifted_bldgs, shifted_roads, shifted_custom_polygon, road_setback=road_setback, building_setback=building_setback, parcel_type=parcel_type)

    # Compute site area and area tier
    area_tier = compute_area_tier(site_area_m2)
    timestamp = int(time.time())
    site_id = f"custom_{area_tier.lower()}_{timestamp}"

    metrics = compute_urban_metrics(shifted_site_verts, shifted_bldgs)

    # Convert parcel center back to exact lat/lon
    slat, slon = local_meters_to_latlon(scx, scy, lat, lon)

    scene_data = {
        'site_id': site_id,
        'city_name': custom_name,
        'coordinates': {'lat': round(slat, 6), 'lon': round(slon, 6)},
        'site_boundary': {'vertices_2d': shifted_site_verts},
        'context_buildings': shifted_bldgs,
        'roads': shifted_roads,
        'metrics': metrics,
        'radius_m': 100.0,
        'debugLayers': debug_layers
    }

    html_name = f"{site_id}.html"
    public_out_path = os.path.join(SITES_DIR, html_name)

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

    print(f"[CustomFetcher] Successfully generated custom 3D site: {site_id} ({area_tier} Tier, {metrics['site_area_m2']} m²)")
    return custom_record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch custom OSM 3D site context")
    parser.add_argument("--lat", type=float, required=True, help="Latitude coordinate")
    parser.add_argument("--lon", type=float, required=True, help="Longitude coordinate")
    parser.add_argument("--name", type=str, default="Custom Site", help="Display name for location")
    parser.add_argument("--polygon", type=str, default=None, help="JSON array of [lat, lon] custom drawn parcel polygon")
    parser.add_argument("--road-setback", type=float, default=2.0, help="Road setback distance in meters")
    parser.add_argument("--building-setback", type=float, default=3.0, help="Building yard setback distance in meters")
    parser.add_argument("--parcel-type", type=str, default="convex_hull", choices=["convex_hull", "voronoi"], help="Base parcel geometry mode")
    args = parser.parse_args()

    poly_list = None
    if args.polygon:
        try:
            poly_list = json.loads(args.polygon)
        except Exception:
            poly_list = None

    res = fetch_custom_site(args.lat, args.lon, args.name, custom_polygon=poly_list, road_setback=args.road_setback, building_setback=args.building_setback, parcel_type=args.parcel_type)
    if res:
        print(json.dumps(res))
    else:
        sys.exit(1)
