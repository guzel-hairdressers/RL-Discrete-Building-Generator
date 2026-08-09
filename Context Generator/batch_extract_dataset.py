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
import numpy as np

import osmnx as ox
from shapely.geometry import Polygon, MultiPolygon, LineString

from config import TARGET_CITIES, DATASET_DIR, OUTPUT_DIR
from geometry_3d import latlon_to_local_meters, extrude_polygon_to_3d_mesh, compute_urban_metrics
from visualizer import create_3d_context_visualization, compute_area_tier

# Configure OSMnx settings for high-volume batch extraction
ox.settings.timeout = 60
ox.settings.overpass_url = "https://overpass-api.de/api/interpreter"


def batch_extract_multi_city(target_count=200, radius_m=100.0, dist_per_city_m=450.0, reset=False):
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
            print(f"[Batch Extractor Warning] Could not parse existing index ({e}). Starting fresh.")
            master_index = []
            global_counter = 1

    cities = list(TARGET_CITIES.keys())
    per_city_target = max(10, math.ceil(target_count / len(cities)))

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

        print(f"\n[Batch Extractor] Mining building sites for {info['name']} (Code: '{city_code}')...")

        try:
            gdf_bldgs = ox.features_from_point((ref_lat, ref_lon), tags={'building': True}, dist=dist_per_city_m)
        except Exception as e:
            print(f"  [Warning] Could not fetch building features for {city_key}: {e}")
            continue

        try:
            gdf_roads = ox.features_from_point((ref_lat, ref_lon), tags={'highway': ['primary', 'secondary', 'tertiary', 'trunk', 'residential']}, dist=dist_per_city_m)
        except Exception as e:
            gdf_roads = None

        if gdf_bldgs is None or len(gdf_bldgs) == 0:
            continue

        # Parse local cartesian buildings
        parsed_bldgs = []
        for idx, row in gdf_bldgs.iterrows():
            geom = row.geometry
            props = row.to_dict()

            if geom is None or geom.is_empty:
                continue

            polys = [geom] if isinstance(geom, Polygon) else (list(geom.geoms) if isinstance(geom, MultiPolygon) else [])

            for poly in polys:
                ext_coords = list(poly.exterior.coords)
                if len(ext_coords) < 3:
                    continue

                local_verts = []
                for lon, lat in ext_coords:
                    mx, my = latlon_to_local_meters(lat, lon, ref_lat, ref_lon)
                    local_verts.append([round(mx, 2), round(my, 2)])

                if len(local_verts) < 3:
                    continue

                height = None
                if "height" in props and str(props["height"]).strip() != "nan":
                    try:
                        val = str(props["height"]).replace("m", "").replace("ft", "").strip()
                        height = float(val)
                    except ValueError:
                        pass

                if height is None and "building:levels" in props and str(props["building:levels"]).strip() != "nan":
                    try:
                        levels = float(props["building:levels"])
                        height = max(6.0, levels * 3.8)
                    except ValueError:
                        pass

                if height is None or height <= 0:
                    height = default_h * np.random.uniform(0.7, 1.3)

                b_name = props.get("name", props.get("building:name", f"Building_{idx}"))
                if str(b_name) == "nan":
                    b_name = f"Building_{idx}"

                centroid = np.mean(np.array(local_verts), axis=0).tolist()
                area_m2 = poly.area * 111000 * 111000

                parsed_bldgs.append({
                    "id": f"bldg_{idx}",
                    "name": str(b_name),
                    "vertices_2d": local_verts,
                    "height": round(height, 1),
                    "centroid": centroid,
                    "area_m2": area_m2,
                    "tags": props
                })

        # Parse road centerlines
        parsed_roads = []
        if gdf_roads is not None:
            for idx, row in gdf_roads.iterrows():
                geom = row.geometry
                props = row.to_dict()
                if geom is None or geom.is_empty:
                    continue
                lines = [geom] if isinstance(geom, LineString) else (list(geom.geoms) if hasattr(geom, "geoms") else [])

                for line in lines:
                    coords = list(line.coords)
                    if len(coords) < 2:
                        continue
                    local_line = []
                    for lon, lat in coords:
                        mx, my = latlon_to_local_meters(lat, lon, ref_lat, ref_lon)
                        local_line.append([round(mx, 2), round(my, 2)])

                    h_type = str(props.get("highway", "street"))
                    r_name = str(props.get("name", f"Street ({h_type})"))
                    if r_name == "nan":
                        r_name = f"Street ({h_type})"

                    parsed_roads.append({
                        "id": f"road_{idx}",
                        "name": r_name,
                        "highway_type": h_type,
                        "width_m": 14.0 if h_type in ["primary", "trunk"] else 8.0,
                        "polyline_2d": local_line
                    })

        # Filter valid site parcels (150 m² <= Area <= 4500 m²)
        valid_candidate_sites = [b for b in parsed_bldgs if 150.0 <= b["area_m2"] <= 4500.0]
        np.random.shuffle(valid_candidate_sites)

        extracted_city_count = 0

        for site_b in valid_candidate_sites:
            if extracted_city_count >= per_city_target or len(master_index) >= target_count:
                break

            scx, scy = site_b["centroid"][0], site_b["centroid"][1]

            ctx_buildings = []
            for b in parsed_bldgs:
                if b["id"] == site_b["id"]:
                    continue
                dist = math.hypot(b["centroid"][0] - scx, b["centroid"][1] - scy)
                if dist <= radius_m + 30.0:
                    ctx_buildings.append(b)

            if len(ctx_buildings) < 4:
                continue

            site_verts = site_b["vertices_2d"]
            metrics = compute_urban_metrics(site_verts, ctx_buildings, radius_m=radius_m)
            area_tier = compute_area_tier(metrics["site_area_m2"])

            num_str = f"{global_counter:04d}"
            tier_code = str(area_tier).lower().replace("-", "")
            candidate_id = f"{tier_code}_{city_code}_{num_str}"
            site_filename = f"{candidate_id}.html"

            if candidate_id in existing_ids:
                print(f"  [Skip] Site {candidate_id} already exists.")
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
                    "centroid": site_b["centroid"],
                },
                "context_buildings": ctx_buildings,
                "roads": parsed_roads,
                "metrics": {
                    "siteArea": metrics["site_area_m2"],
                    "areaTier": area_tier,
                    "far": metrics["floor_area_ratio"],
                    "buildingCount": len(ctx_buildings),
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
                "building_count": len(ctx_buildings),
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
