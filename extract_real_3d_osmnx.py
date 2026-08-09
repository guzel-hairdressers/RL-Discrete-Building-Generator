"""
Robust OSMnx 3D Urban Context Extractor.
Parses exact building footprints, building parts, building levels, and heights from OSM via OSMnx,
extruding real 3D skyscraper geometry for NYC Midtown, Tokyo Shinjuku, and target cities.
"""

import json
import math
import os
import sys
import numpy as np

import shapely
from shapely.geometry import Polygon, MultiPolygon, LineString

import osmnx as ox

from config import TARGET_CITIES, DATASET_DIR, OUTPUT_DIR
from geometry_3d import latlon_to_local_meters, extrude_polygon_to_3d_mesh, compute_urban_metrics
from visualizer import create_3d_context_visualization
from exporter import export_context_to_obj


def extract_city_osmnx_3d(city_key, radius_m=160.0):
    if city_key not in TARGET_CITIES:
        print(f"Unknown city key '{city_key}'. Available: {list(TARGET_CITIES.keys())}")
        return

    info = TARGET_CITIES[city_key]
    ref_lat, ref_lon = info["lat"], info["lon"]
    default_h = info.get("default_height", 60.0)

    print(f"\n[OSMnx 3D Extractor] Downloading real 3D urban geometry for {info['name']}...")
    print(f"  - Center: Lat {ref_lat}, Lon {ref_lon} | Radius: {radius_m}m")

    try:
        gdf_bldgs = ox.features_from_point((ref_lat, ref_lon), tags={'building': True}, dist=radius_m)
    except Exception as e:
        print(f"[OSMnx Error] Could not fetch building features: {e}")
        return

    try:
        gdf_roads = ox.features_from_point((ref_lat, ref_lon), tags={'highway': ['primary', 'secondary', 'tertiary', 'trunk', 'residential']}, dist=radius_m)
    except Exception as e:
        print(f"[OSMnx Warning] Could not fetch road network: {e}")
        gdf_roads = None

    print(f"[OSMnx Success] Fetched {len(gdf_bldgs)} building features!")

    context_buildings = []

    for idx, row in gdf_bldgs.iterrows():
        geom = row.geometry
        props = row.to_dict()

        if geom is None or geom.is_empty:
            continue

        polys = []
        if isinstance(geom, Polygon):
            polys = [geom]
        elif isinstance(geom, MultiPolygon):
            polys = list(geom.geoms)

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
                area = poly.area * 111000 * 111000
                if area > 2000:
                    height = default_h * 1.4
                elif area > 800:
                    height = default_h * 1.0
                else:
                    height = default_h * 0.65

            b_name = props.get("name", props.get("building:name", f"Building_{idx}"))
            if str(b_name) == "nan":
                b_name = f"Building_{idx}"

            centroid = np.mean(np.array(local_verts), axis=0).tolist()
            dist = math.hypot(centroid[0], centroid[1])

            mesh_3d = extrude_polygon_to_3d_mesh(local_verts, height)
            if mesh_3d:
                context_buildings.append({
                    "id": f"bldg_{idx}",
                    "name": str(b_name),
                    "vertices_2d": local_verts,
                    "height": round(height, 1),
                    "mesh_3d": mesh_3d,
                    "centroid": centroid,
                    "dist_to_center": dist
                })

    context_buildings.sort(key=lambda b: b["dist_to_center"])

    if not context_buildings:
        print("[OSMnx Error] No valid 3D building polygons extracted.")
        return

    site_b = context_buildings[0]
    site_verts = site_b["vertices_2d"]

    parsed_roads = []
    if gdf_roads is not None:
        for idx, row in gdf_roads.iterrows():
            geom = row.geometry
            props = row.to_dict()

            if geom is None or geom.is_empty:
                continue

            lines = []
            if isinstance(geom, LineString):
                lines = [geom]
            elif hasattr(geom, "geoms"):
                lines = list(geom.geoms)

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

    metrics = compute_urban_metrics(site_verts, context_buildings[1:], radius_m=radius_m)

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
        "radius_m": radius_m,
        "site_boundary": {
            "name": site_b["name"],
            "vertices_2d": site_verts,
            "centroid": site_b["centroid"],
            "original_height": site_b["height"]
        },
        "context_buildings": context_buildings[1:],
        "roads": parsed_roads,
        "metrics": metrics
    }

    dataset_path = os.path.join(DATASET_DIR, f"{city_key}_context.json")
    with open(dataset_path, "w") as f:
        clean_data = json.loads(json.dumps(context_scene, default=lambda o: o.tolist() if isinstance(o, np.ndarray) else o))
        json.dump(clean_data, f, indent=2)

    print(f"[OSMnx Success] Extracted {len(context_buildings)-1} 3D Skyscraper/Building blocks & {len(parsed_roads)} road segments!")
    print(f"  - Site Parcel: {site_b['name']} ({metrics['site_area_m2']} m²)")
    print(f"  - Max Height: {metrics['max_height_m']}m | Avg Height: {metrics['avg_height_m']}m | FAR: {metrics['floor_area_ratio']}")

    html_out = os.path.join(OUTPUT_DIR, f"{city_key}_3d.html")
    obj_out = os.path.join(OUTPUT_DIR, f"{city_key}_3d.obj")
    create_3d_context_visualization(context_scene, html_out)
    export_context_to_obj(context_scene, obj_out)
    print(f"[Render Success] Saved real 3D WebGL scene to: {html_out}")
    print(f"[Export Success] Saved 3D OBJ mesh to: {obj_out}")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "nyc_midtown"
    extract_city_osmnx_3d(target)
