"""
Automated Batch Urban Context Dataset Extractor.
Extracts 200 to 500+ diverse 3D building sites & 200m x 200m urban contexts
across a multi-city global portfolio (NYC, Tokyo, Barcelona, London, Chicago, Hong Kong, Paris, Singapore).

Filenames are automatically formatted as tier_citycode_num.html (e.g. ml_nyc_0003.html, s_tokyo_0042.html).

Usage:
  python batch_extract_dataset.py --target-count 200
  python batch_extract_dataset.py --target-count 500
"""

import argparse
import json
import math
import os
import sys
import time
import requests
import numpy as np

from shapely.geometry import Polygon, MultiPolygon, LineString

from config import TARGET_CITIES, DATASET_DIR, OUTPUT_DIR
from geometry_3d import latlon_to_local_meters, extrude_polygon_to_3d_mesh, compute_urban_metrics
from visualizer import create_3d_context_visualization, compute_area_tier

# Overpass API mirrors for fallback
OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.ai/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.nchc.org.tw/api/interpreter"
]


def fetch_overpass_features(ref_lat, ref_lon, dist_m=500.0):
    """Fetch building features from Overpass API with server fallback."""
    query = f"""
    [out:json][timeout:30];
    (
      way["building"](around:{dist_m},{ref_lat},{ref_lon});
      relation["building"](around:{dist_m},{ref_lat},{ref_lon});
    );
    out body;
    >;
    out skel qt;
    """

    for server in OVERPASS_SERVERS:
        try:
            resp = requests.post(server, data={"data": query}, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if "elements" in data and len(data["elements"]) > 0:
                    return data
        except Exception:
            continue
        time.sleep(0.5)

    return None


def parse_overpass_json_to_bldgs(data, ref_lat, ref_lon, default_h=50.0):
    if not data or "elements" not in data:
        return []

    nodes = {e["id"]: (e["lat"], e["lon"]) for e in data["elements"] if e["type"] == "node"}
    buildings = []

    for idx, elem in enumerate(data["elements"]):
        if elem["type"] == "way" and "nodes" in elem:
            coords = [nodes[nid] for nid in elem["nodes"] if nid in nodes]
            if len(coords) < 3:
                continue

            local_verts = []
            for lat, lon in coords:
                mx, my = latlon_to_local_meters(lat, lon, ref_lat, ref_lon)
                local_verts.append([round(mx, 2), round(my, 2)])

            if len(local_verts) < 3:
                continue

            props = elem.get("tags", {})
            height = None
            if "height" in props:
                try:
                    val = str(props["height"]).replace("m", "").replace("ft", "").strip()
                    height = float(val)
                except ValueError:
                    pass

            if height is None and "building:levels" in props:
                try:
                    levels = float(props["building:levels"])
                    height = max(6.0, levels * 3.8)
                except ValueError:
                    pass

            if height is None or height <= 0:
                height = default_h * np.random.uniform(0.7, 1.3)

            b_name = props.get("name", props.get("building:name", f"Building_{elem['id']}"))
            centroid = np.mean(np.array(local_verts), axis=0).tolist()

            try:
                poly = Polygon(local_verts)
                area_m2 = poly.area
            except Exception:
                area_m2 = 400.0

            buildings.append({
                "id": f"bldg_{elem['id']}",
                "name": str(b_name),
                "vertices_2d": local_verts,
                "height": round(height, 1),
                "centroid": centroid,
                "area_m2": area_m2,
                "tags": props
            })

    return buildings


def batch_extract_multi_city(target_count=200, radius_m=100.0, dist_per_city_m=500.0, reset=False):
    master_json_path = os.path.join(DATASET_DIR, "master_urban_dataset.json")
    master_index = []
    global_counter = 1
    existing_ids = set()

    if reset:
        print("[Batch Extractor Reset] Resetting dataset index and starting fresh from site #1...")
        if os.path.exists(master_json_path):
            os.remove(master_json_path)
    elif os.path.exists(master_json_path):
        try:
            with open(master_json_path, "r") as f:
                master_index = json.load(f)
            global_counter = len(master_index) + 1
            existing_ids = {item["site_id"] for item in master_index if "site_id" in item}
            print(f"[Batch Extractor Resume] Resuming extraction from site #{global_counter} ({len(master_index)} sites already extracted)...")
        except Exception as e:
            master_index = []
            global_counter = 1

    cities = list(TARGET_CITIES.keys())
    per_city_target = max(15, math.ceil(target_count / len(cities)))

    print("=" * 70)
    print(f"   AUTOMATED BATCH URBAN CONTEXT EXTRACTOR (Target: {target_count} Sites)")
    print(f"   Multi-City Portfolio: {', '.join([TARGET_CITIES[c]['city_code'].upper() for c in cities])}")
    print(f"   Bounding Area: 200m x 200m (Radius: {radius_m}m)")
    print("=" * 70)

    for city_key in cities:
        if len(master_index) >= target_count:
            break

        info = TARGET_CITIES[city_key]
        city_code = info["city_code"]
        ref_lat, ref_lon = info["lat"], info["lon"]
        default_h = info.get("default_height", 50.0)

        dataset_cache = os.path.join(DATASET_DIR, f"{city_key}_context.json")

        if os.path.exists(dataset_cache):
            print(f"\n[Batch Extractor Cache] Slicing site parcels offline from: {dataset_cache}")
            with open(dataset_cache, "r") as f:
                cached_data = json.load(f)

            parsed_bldgs = []
            for idx, b in enumerate(cached_data.get("context_buildings", [])):
                verts = b.get("vertices_2d", [])
                if len(verts) >= 3:
                    try:
                        poly = Polygon(verts)
                        area = poly.area
                    except Exception:
                        area = 400.0

                    parsed_bldgs.append({
                        "id": f"cached_bldg_{idx}",
                        "name": b.get("name", f"Building_{idx}"),
                        "vertices_2d": verts,
                        "height": b.get("height", default_h),
                        "centroid": b.get("centroid", np.mean(verts, axis=0).tolist()),
                        "area_m2": area,
                    })
            parsed_roads = cached_data.get("roads", [])
        else:
            print(f"\n[Batch Extractor Online] Fetching 3D urban features for {info['name']} (Code: '{city_code}')...")
            overpass_raw = fetch_overpass_features(ref_lat, ref_lon, dist_m=dist_per_city_m)
            parsed_bldgs = parse_overpass_json_to_bldgs(overpass_raw, ref_lat, ref_lon, default_h=default_h)
            parsed_roads = []

        if len(parsed_bldgs) == 0:
            print(f"  [Warning] No building features parsed for {city_key}.")
            continue

        # Filter valid site parcels (150 m² <= Area <= 4500 m²)
        valid_candidate_sites = [b for b in parsed_bldgs if 150.0 <= b["area_m2"] <= 4500.0]
        np.random.shuffle(valid_candidate_sites)

        extracted_city_count = 0

        for site_b in valid_candidate_sites:
            if extracted_city_count >= per_city_target or len(master_index) >= target_count:
                break

            scx, scy = site_b["centroid"][0], site_b["centroid"][1]

            # Shift coordinate origin to current site parcel center
            shifted_bldgs = []
            ctx_bldgs = []

            for b in parsed_bldgs:
                if b["id"] == site_b["id"]:
                    continue

                dist = math.hypot(b["centroid"][0] - scx, b["centroid"][1] - scy)
                if dist <= radius_m + 25.0:  # 100m radius cutoff = 200m x 200m box
                    shifted_verts = [[round(vx - scx, 2), round(vy - scy, 2)] for vx, vy in b["vertices_2d"]]
                    shifted_bldgs.append({
                        "id": b["id"],
                        "name": b["name"],
                        "vertices_2d": shifted_verts,
                        "height": b["height"],
                        "centroid": [round(b["centroid"][0] - scx, 2), round(b["centroid"][1] - scy, 2)],
                        "area_m2": b["area_m2"]
                    })

            if len(shifted_bldgs) < 4:
                continue

            site_verts = [[round(vx - scx, 2), round(vy - scy, 2)] for vx, vy in site_b["vertices_2d"]]
            metrics = compute_urban_metrics(site_verts, shifted_bldgs, radius_m=radius_m)
            area_tier = compute_area_tier(metrics["site_area_m2"])

            num_str = f"{global_counter:04d}"
            tier_code = str(area_tier).lower().replace("-", "")
            candidate_id = f"{tier_code}_{city_code}_{num_str}"
            site_filename = f"{candidate_id}.html"

            if candidate_id in existing_ids:
                continue

            html_out_path = os.path.join(OUTPUT_DIR, site_filename)

            scene_data = {
                "site_id": candidate_id,
                "city_key": city_key,
                "city_code": city_code,
                "city_name": info["name"],
                "typology": info["typology"],
                "density_class": info["density_class"],
                "coordinates": {"lat": ref_lat, "lon": ref_lon},
                "radius_m": radius_m,
                "site_boundary": {
                    "name": site_b["name"],
                    "vertices_2d": site_verts,
                    "centroid": [0.0, 0.0],
                },
                "context_buildings": shifted_bldgs,
                "roads": [],
                "metrics": {
                    "siteArea": metrics["site_area_m2"],
                    "areaTier": area_tier,
                    "far": metrics["floor_area_ratio"],
                    "buildingCount": len(shifted_bldgs),
                    "maxHeight": metrics["max_height_m"],
                    "avgHeight": metrics["avg_height_m"],
                }
            }

            create_3d_context_visualization(scene_data, html_out_path)

            record = {
                "site_id": candidate_id,
                "city_code": city_code,
                "city_name": info["name"],
                "area_tier": area_tier,
                "site_area_m2": metrics["site_area_m2"],
                "avg_height_m": metrics["avg_height_m"],
                "max_height_m": metrics["max_height_m"],
                "building_count": len(shifted_bldgs),
                "render_html": f"output/{site_filename}"
            }

            master_index.append(record)
            existing_ids.add(candidate_id)
            global_counter += 1
            extracted_city_count += 1

            # Save incremental index update to disk after EVERY site
            with open(master_json_path, "w") as f:
                json.dump(master_index, f, indent=2)

            print(f"  [Extracted {global_counter-1}/{target_count}] Saved {site_filename} ({metrics['site_area_m2']} m², {area_tier} Tier)")

    print("\n" + "=" * 70)
    print(f"[Batch Extractor Complete] Total site contexts in dataset: {len(master_index)}")
    print(f"  - Master Dataset Index: {master_json_path}")
    print(f"  - Output HTML Folder: {OUTPUT_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stateful Batch Extractor for 200-500 Urban Context Sites")
    parser.add_argument("--target-count", type=int, default=200, help="Total number of sites to extract (e.g. 200 or 500)")
    parser.add_argument("--radius", type=float, default=100.0, help="Context radius in meters (default 100.0 = 200m x 200m)")
    parser.add_argument("--resume", action="store_true", default=True, help="Resume extraction from existing dataset index (default: True)")
    parser.add_argument("--reset", action="store_true", help="Reset dataset index and start over from scratch")
    args = parser.parse_args()

    batch_extract_multi_city(target_count=args.target_count, radius_m=args.radius, reset=args.reset)
