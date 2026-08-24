"""
Architectural 3D WebGL Visualizer for Context Generator.
Implements clean architectural diagram style matching Bauhaus / Sequence.Dense:
- 100% Pure Paper White (#ffffff) for all un-shadowed roofs, ground, roads, and sun-facing building walls.
- Strict Normal-Filtered Cast Shadow Overlay: ShadowMaterial overlay ONLY includes sun-facing faces (N·L > 0.05). Back-facing unlit walls (N·L <= 0.05) are 100% EXCLUDED from shadow map reception and rendered in a uniform, crisp architectural shadow color (#d8dfe8). Zero cast shadow bleeding across unlit walls!
- Cast shadows on ground and roads project smoothly via ShadowMaterial overlay (depthWrite=false).
- Custom interactive Blender 3D Orientation Gizmo widget positioned RIGHT BELOW the top-right controls bar (top: 72px, right: 20px).
- Perfect Blender Axis Mapping: Z = Blue (#3b82f6), X = Red (#ef4444), Y = Green (#22c55e).
- Gizmo axis clicks work 100% FLAWLESSLY in BOTH Perspective and Axonometric camera modes!
- Top-right controls bar contains ONLY Axonometric and Perspective mode toggle buttons.
- True 100% orthographic elevation views (Top, Front, Right, Left, Back) with ZERO vertical angle bias.
- Snappy camera rotation easing (controls.dampingFactor = 0.18).
- Clean vector edge outlines (#999999 for buildings, #d1d5db for roads).
- Non-bold solid black scale tick labels (font: 400 20px Inter) on ALL 4 SIDES of the boundary box.
- Clean architectural building tooltips (Function/Use, Footprint Area, Estimated Floors, Height).
"""

import os
import json
import numpy as np

try:
    from shapely.geometry import Polygon, LineString, MultiPolygon, box
    from shapely.geometry.polygon import orient
    from shapely.ops import unary_union
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False

try:
    import trimesh
    TRIMESH_AVAILABLE = True
except ImportError:
    TRIMESH_AVAILABLE = False

from geometry_3d import ensure_ccw_polygon


NON_VEHICULAR_HIGHWAYS = {
    "footway", "pedestrian", "steps", "path", "sidewalk", "cycleway",
    "bridleway", "corridor", "proposed", "construction", "platform",
    "track", "footpath"
}


def compute_area_tier(area_m2):
    """
    Categorize site by area:
        XS : area < 600 m²
        S  : 600 <= area < 1,200 m²
        M  : 1,200 <= area < 2,500 m²
        L  : 2,500 <= area < 4,000 m²
        XL : area >= 4,000 m²
    """
    if area_m2 < 600.0:
        return "XS"
    elif area_m2 < 1200.0:
        return "S"
    elif area_m2 < 2500.0:
        return "M"
    elif area_m2 < 4000.0:
        return "L"
    else:
        return "XL"


def _parse_building_function(tags, height):
    """Parse rich building function/typology from OSM tags or infer from height/geometry."""
    tags = tags or {}
    b_tag = str(tags.get("building", "yes")).lower()
    amenity = str(tags.get("amenity", "")).lower()
    shop = str(tags.get("shop", "")).lower()
    office = str(tags.get("office", "")).lower()
    use_tag = str(tags.get("building:use", "")).lower()

    if amenity in ("school", "university", "college", "kindergarten"):
        return "Educational Institution"
    if amenity in ("hospital", "clinic", "doctors"):
        return "Healthcare Facility"
    if amenity in ("place_of_worship", "church", "temple", "mosque"):
        return "Civic & Cultural"
    if amenity in ("townhall", "police", "courthouse", "fire_station"):
        return "Public & Civic Facility"
    if shop or amenity in ("restaurant", "cafe", "bank", "fast_food", "bar"):
        return "Commercial / Retail"
    if office or b_tag in ("office", "commercial"):
        return "Office / Commercial"
    if b_tag in ("apartments", "dormitory"):
        return "Residential Apartments"
    if b_tag in ("house", "detached", "semidetached_house", "terrace", "residential"):
        return "Residential Housing"
    if b_tag in ("hotel", "hostel", "motel"):
        return "Hospitality / Hotel"
    if b_tag in ("industrial", "warehouse", "factory"):
        return "Industrial & Logistics"

    if use_tag and use_tag not in ("yes", "true"):
        return use_tag.replace("_", " ").title()

    # Smart inference for generic tags
    if height >= 50.0:
        return "Highrise Commercial / Mixed-Use"
    elif height >= 25.0:
        return "Midrise Commercial / Office"
    else:
        return "Residential / Mixed-Use"


def _clean_to_shapely(vertices_2d):
    """Convert raw 2D vertices into a clean shapely Polygon."""
    verts = list(vertices_2d)
    if len(verts) < 3:
        return None
    if len(verts) > 1 and np.allclose(verts[0], verts[-1], atol=0.01):
        verts = verts[:-1]
    if len(verts) < 3:
        return None
    try:
        poly = Polygon(verts)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.geom_type == 'MultiPolygon':
            poly = max(poly.geoms, key=lambda g: g.area)
        if poly.is_empty or poly.area < 1.0:
            return None
        poly = orient(poly, sign=1.0)
        return poly
    except Exception:
        return None


def _clip_polygon_to_box(poly, center, half_size):
    """Clip a shapely polygon to a square boundary centered at center."""
    clip_box = box(center[0] - half_size, center[1] - half_size,
                   center[0] + half_size, center[1] + half_size)
    try:
        clipped = poly.intersection(clip_box)
        if clipped.is_empty or clipped.area < 1.0:
            return None
        if clipped.geom_type == 'MultiPolygon':
            clipped = max(clipped.geoms, key=lambda g: g.area)
        if clipped.geom_type != 'Polygon':
            return None
        return clipped
    except Exception:
        return None


def _extrude_polygon(poly, height):
    """Extrude a shapely polygon to a 3D trimesh mesh. Returns (verts, faces) or None."""
    if not TRIMESH_AVAILABLE:
        return None
    try:
        mesh = trimesh.creation.extrude_polygon(poly, height)
        if mesh is None or len(mesh.vertices) == 0:
            return None
        mesh.fix_normals()
        return mesh.vertices.tolist(), mesh.faces.tolist()
    except Exception:
        return None


def _build_road_network_polygons(roads, center, half_size):
    """
    Convert vehicular road centerlines into connected polygonal road surfaces with proper widths & fillet junctions.
    Extracts outer perimeter boundaries ONLY to eliminate all internal transverse seam lines/cuts!
    """
    if not roads or not SHAPELY_AVAILABLE:
        return {"meshes": [], "outlines": []}
    clip_box = box(center[0] - half_size, center[1] - half_size,
                   center[0] + half_size, center[1] + half_size)
    road_polys = []
    for r in roads:
        h_type = r.get("highway_type", "")
        if h_type in NON_VEHICULAR_HIGHWAYS:
            continue

        pts = r.get("polyline_2d", r.get("points_2d", []))
        if len(pts) < 2:
            continue
        width = r.get("width_m", 6.0)
        try:
            line = LineString(pts)
            r_poly = line.buffer(width / 2.0, cap_style='round', join_style='round')
            if not r_poly.is_valid:
                r_poly = r_poly.buffer(0)
            clipped = r_poly.intersection(clip_box)
            if not clipped.is_empty:
                if clipped.geom_type == 'Polygon':
                    road_polys.append(clipped)
                elif clipped.geom_type == 'MultiPolygon':
                    road_polys.extend(list(clipped.geoms))
        except Exception:
            pass

    if not road_polys:
        return {"meshes": [], "outlines": []}

    try:
        merged = unary_union(road_polys)
        if merged.geom_type == 'Polygon':
            merged_list = [merged]
        elif merged.geom_type == 'MultiPolygon':
            merged_list = list(merged.geoms)
        else:
            merged_list = road_polys
    except Exception:
        merged_list = road_polys

    road_meshes = []
    road_outlines = []
    for rp in merged_list:
        if rp.is_empty or rp.area < 1.0:
            continue
        res = _extrude_polygon(rp, 0.01) # Flat 2D surface on ground
        if res is not None:
            rv, rf = res
            rv = [[v[0] - center[0], v[1] - center[1], v[2]] for v in rv]
            road_meshes.append({"vertices": rv, "faces": rf})

            # Extract outer perimeter boundary coordinates
            if hasattr(rp, "exterior") and rp.exterior:
                ext_coords = [[p[0] - center[0], p[1] - center[1]] for p in list(rp.exterior.coords)]
                road_outlines.append(ext_coords)
            if hasattr(rp, "interiors"):
                for hole in rp.interiors:
                    hole_coords = [[p[0] - center[0], p[1] - center[1]] for p in list(hole.coords)]
                    road_outlines.append(hole_coords)

    return {"meshes": road_meshes, "outlines": road_outlines}


def create_3d_context_visualization(scene, output_path=None):
    """Generate an architectural WebGL visualization with orthographic/perspective controls, outlines, and soft shadows."""
    if not SHAPELY_AVAILABLE or not TRIMESH_AVAILABLE:
        print("[Visualizer] Error: shapely and trimesh required.")
        return None

    buildings = scene["context_buildings"]
    roads = scene.get("roads", [])
    green_spaces = scene.get("green_spaces", scene.get("parks", []))
    metrics = scene["metrics"]
    city_name = scene.get("city_name", scene.get("density_class", "Urban Context"))
    coords = scene.get("coordinates", {})
    radius = scene.get("radius_m", 100.0)

    # --- Center on the site boundary ---
    site_verts = scene["site_boundary"]["vertices_2d"]
    site_poly = _clean_to_shapely(site_verts)
    if site_poly is not None:
        cx, cy = site_poly.centroid.x, site_poly.centroid.y
        site_area = round(site_poly.area, 1)
        site_boundary_coords = [[p[0] - cx, p[1] - cy] for p in list(site_poly.exterior.coords)]
    else:
        cx, cy = 0.0, 0.0
        site_area = metrics.get("site_area_m2", 0)
        site_boundary_coords = []

    area_tier = compute_area_tier(site_area)
    clip_center = (cx, cy)

    # --- Process context buildings with rich metadata ---
    max_h = max([b.get("height", b.get("height_m", 30.0)) for b in buildings]) if buildings else 100.0
    building_meshes = []

    for idx, b in enumerate(buildings):
        raw_verts = b.get("vertices_2d", b.get("vertices", []))
        h = max(4.0, float(b.get("height", b.get("height_m", 30.0))))

        poly = _clean_to_shapely(raw_verts)
        if poly is None:
            continue

        b_area = round(float(poly.area), 1)

        # Subtract site parcel so test site is NEVER covered
        if site_poly is not None and poly.intersects(site_poly):
            try:
                poly = poly.difference(site_poly)
                if poly.is_empty or poly.area < 1.0:
                    continue
                if poly.geom_type == 'MultiPolygon':
                    poly = max(poly.geoms, key=lambda g: g.area)
            except Exception:
                pass

        clipped = _clip_polygon_to_box(poly, clip_center, radius)
        if clipped is None:
            continue

        result = _extrude_polygon(clipped, h)
        if result is None:
            continue

        verts, faces = result
        verts = [[v[0] - cx, v[1] - cy, v[2]] for v in verts]

        # Extract rich building typology/function
        tags = b.get("tags", {})
        b_use = _parse_building_function(tags, h)
        b_floors = max(1, round(h / 3.5))

        building_meshes.append({
            "vertices": verts,
            "faces": faces,
            "height": round(h, 1),
            "area": b_area,
            "floors": b_floors,
            "use": b_use,
        })

    # --- Process site parcel ---
    site_mesh = None
    if site_poly is not None:
        clipped_site = _clip_polygon_to_box(site_poly, clip_center, radius)
        if clipped_site is None:
            clipped_site = site_poly
        result = _extrude_polygon(clipped_site, 0.2)
        if result is not None:
            sv, sf = result
            sv = [[v[0] - cx, v[1] - cy, v[2]] for v in sv]
            site_mesh = {"vertices": sv, "faces": sf}

    # --- Process road network polygons ---
    road_data = _build_road_network_polygons(roads, clip_center, radius)

    # --- Process green spaces ---
    green_meshes = []
    for g_item in green_spaces:
        g_verts = g_item.get("vertices_2d", [])
        g_poly = _clean_to_shapely(g_verts)
        if g_poly is None:
            continue
        g_clipped = _clip_polygon_to_box(g_poly, clip_center, radius)
        if g_clipped is None:
            continue
        g_res = _extrude_polygon(g_clipped, 0.1)
        if g_res is not None:
            gv, gf = g_res
            gv = [[v[0] - cx, v[1] - cy, v[2]] for v in gv]
            green_meshes.append({"vertices": gv, "faces": gf})

    # Calculate robust average & max heights directly from actual prepared building meshes
    actual_heights = [b["height"] for b in building_meshes if "height" in b]
    calc_avg_h = float(np.mean(actual_heights)) if actual_heights else float(metrics.get("avgHeight", metrics.get("avg_height_m", 0.0)))
    calc_max_h = float(np.max(actual_heights)) if actual_heights else float(metrics.get("maxHeight", metrics.get("max_height_m", max_h)))

    raw_debug = scene.get("debugLayers", scene.get("debug_layers", {}))
    centered_debug = {}
    if "convex_hull" in raw_debug and raw_debug["convex_hull"]:
        centered_debug["convex_hull"] = [[p[0] - cx, p[1] - cy] for p in raw_debug["convex_hull"]]
    if "setback_buffer" in raw_debug and raw_debug["setback_buffer"]:
        centered_debug["setback_buffer"] = [[p[0] - cx, p[1] - cy] for p in raw_debug["setback_buffer"]]
    if "road_setbacks" in raw_debug and raw_debug["road_setbacks"]:
        centered_debug["road_setbacks"] = [[[p[0] - cx, p[1] - cy] for p in poly] for poly in raw_debug["road_setbacks"]]
    if "voronoi_all_cells" in raw_debug and raw_debug["voronoi_all_cells"]:
        centered_debug["voronoi_all_cells"] = [[[p[0] - cx, p[1] - cy] for p in cell] for cell in raw_debug["voronoi_all_cells"]]
    if "voronoi_target_cell" in raw_debug and raw_debug["voronoi_target_cell"]:
        centered_debug["voronoi_target_cell"] = [[p[0] - cx, p[1] - cy] for p in raw_debug["voronoi_target_cell"]]
    if "voronoi_centroids" in raw_debug and raw_debug["voronoi_centroids"]:
        centered_debug["voronoi_centroids"] = [[p[0] - cx, p[1] - cy] for p in raw_debug["voronoi_centroids"]]

    scene_data = json.dumps({
        "buildings": building_meshes,
        "site": site_mesh,
        "sitePerimeter": site_boundary_coords,
        "roads": road_data["meshes"],
        "roadOutlines": road_data["outlines"],
        "greenSpaces": green_meshes,
        "siteArea": site_area,
        "areaTier": area_tier,
        "radius": radius,
        "maxHeight": round(calc_max_h, 1),
        "cityName": city_name,
        "coords": coords,
        "debugLayers": centered_debug,
        "metrics": {
            "siteArea": site_area,
            "areaTier": area_tier,
            "far": metrics.get("floor_area_ratio", metrics.get("far", "?")),
            "buildingCount": metrics.get("building_count", len(building_meshes)),
            "maxHeight": round(calc_max_h, 1),
            "avgHeight": round(calc_avg_h, 1),
            "maxFloors": max(1, int(round(calc_max_h / 3.8))),
            "avgFloors": max(1, int(round(calc_avg_h / 3.8))),
        },
    }, separators=(',', ':'))

    html = _generate_architectural_threejs_html(scene_data)

    if output_path is None:
        tier_str = str(area_tier).lower().replace("-", "")
        city_code = scene.get("city_code", scene.get("city_key", "nyc")).split("_")[0]
        site_id_str = str(scene.get("site_id", "0001")).replace("site_", "")
        output_path = os.path.join(os.path.dirname(__file__), "output", f"{tier_str}_{city_code}_{site_id_str}.html")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w") as f:
        f.write(html)

    print(f"[Visualizer] Saved architectural render to: {output_path}")
    return output_path


def _generate_architectural_threejs_html(scene_data_json):
    """Generate lightweight modular architectural diagram viewer HTML referencing shared JS/CSS."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Urban Context Architectural Diagram</title>
<link rel="stylesheet" href="/styles/urban_viewer.css">
</head>
<body>

<div id="gizmo-container"></div>
<div id="tooltip"></div>

<script type="module">
import {{ initUrbanContext }} from '/scripts/urban_viewer.js';

const DATA = {scene_data_json};
initUrbanContext(DATA);
</script>
</body>
</html>"""
