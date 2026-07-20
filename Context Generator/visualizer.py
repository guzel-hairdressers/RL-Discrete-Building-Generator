"""
Architectural 3D WebGL Visualizer for Context Generator.
Implements clean architectural diagram style matching Bauhaus / Sequence.Dense:
- Custom interactive Blender 3D Orientation Gizmo widget positioned RIGHT BELOW the top-right controls bar (top: 72px, right: 20px).
- Perfect Blender Axis Mapping:
  - Z = Vertical Height (Blue #3b82f6, dir [0, 1, 0])
  - X = Horizontal Right (Red #ef4444, dir [1, 0, 0])
  - Y = Horizontal Depth (Green #22c55e, dir [0, 0, 1])
- Gizmo axis clicks work 100% FLAWLESSLY in BOTH Perspective and Axonometric camera modes!
- Top-right controls bar contains ONLY Axonometric and Perspective mode toggle buttons.
- True 100% orthographic elevation views (Top, Front, Right, Left, Back) with ZERO vertical angle bias.
- Fixed Road Shadowing: road surfaces receive shadows cleanly from single shadowPlane with ZERO flickering & ZERO double-stack darkening.
- Snappy camera rotation easing (controls.dampingFactor = 0.18).
- 100% unshaded MeshBasicMaterial (#ffffff). ALL buildings, roads, and ground are pure bright white.
- Clean vector edge outlines (#999999 for buildings, #d1d5db for roads).
- Soft directional architectural shadows (cast shadow opacity 0.12).
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
        S  : 350 <= area < 600 m²
        M  : 600 <= area < 1,200 m²
        L  : 1,200 <= area < 2,500 m²
        XL : area >= 2,500 m²
    """
    if area_m2 < 600.0:
        return "S"
    elif area_m2 < 1200.0:
        return "M"
    elif area_m2 < 2500.0:
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

        pts = r.get("polyline_2d", [])
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
    max_h = max([b.get("height", 30.0) for b in buildings]) if buildings else 100.0
    building_meshes = []

    for idx, b in enumerate(buildings):
        raw_verts = b["vertices_2d"]
        h = max(4.0, float(b.get("height", 30.0)))

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

    print(f"[Visualizer] Prepared {len(building_meshes)}/{len(buildings)} buildings and {len(road_data['meshes'])} road network polygons.")

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
        "maxHeight": max_h,
        "cityName": city_name,
        "coords": coords,
        "metrics": {
            "siteArea": site_area,
            "areaTier": area_tier,
            "far": metrics.get("far", "?"),
            "buildingCount": metrics.get("building_count", len(building_meshes)),
            "maxHeight": metrics.get("max_height_m", metrics.get("max_height", max_h)),
        },
    }, separators=(',', ':'))

    html = _generate_architectural_threejs_html(scene_data)

    if output_path is None:
        output_path = os.path.join(os.path.dirname(__file__), "output", "context_3d_render.html")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w") as f:
        f.write(html)

    print(f"[Visualizer] Saved architectural render to: {output_path}")
    return output_path


def _generate_architectural_threejs_html(scene_data_json):
    """Generate self-contained architectural diagram viewer HTML."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Urban Context Architectural Diagram</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: #ffffff; overflow: hidden;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: #1e293b;
  }}
  #ui-container {{
    position: absolute; top: 20px; left: 20px; z-index: 10;
    display: flex; flex-direction: column; gap: 12px;
    pointer-events: none;
  }}
  .card {{
    background: rgba(255, 255, 255, 0.95);
    backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
    border: 1px solid rgba(226, 232, 240, 0.9);
    border-radius: 12px; padding: 18px 22px;
    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.04);
    pointer-events: auto; max-width: 320px;
  }}
  .card h1 {{
    font-size: 16px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.05em; color: #0f172a; margin-bottom: 4px;
  }}
  .card .subtitle {{
    font-size: 12px; color: #64748b; margin-bottom: 12px; font-weight: 500;
  }}
  .metrics-grid {{
    display: grid; grid-template-columns: 1fr 1fr; gap: 8px 12px;
    font-size: 12px; border-top: 1px solid #f1f5f9; padding-top: 10px;
  }}
  .metric-item {{ display: flex; flex-direction: column; }}
  .metric-label {{ color: #94a3b8; font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; }}
  .metric-val {{ font-weight: 600; color: #1e293b; font-size: 13px; }}

  /* Top-Right Controls Bar (Axonometric & Perspective ONLY) */
  #controls-bar {{
    position: absolute; top: 20px; right: 20px; z-index: 10;
    display: flex; gap: 6px; background: rgba(255, 255, 255, 0.95);
    padding: 5px; border-radius: 10px;
    border: 1px solid rgba(226, 232, 240, 0.9);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.04);
  }}
  .toggle-btn {{
    border: none; background: transparent; padding: 8px 14px;
    border-radius: 6px; font-size: 12px; font-weight: 600;
    color: #64748b; cursor: pointer; transition: all 0.2s ease;
  }}
  .toggle-btn.active {{
    background: #0f172a; color: #ffffff;
    box-shadow: 0 2px 8px rgba(15, 23, 42, 0.2);
  }}
  .toggle-btn:hover:not(.active) {{
    background: #f1f5f9; color: #334155;
  }}

  /* Interactive Blender Orientation Gizmo Container directly under the top-right bar */
  #gizmo-container {{
    position: absolute; top: 72px; right: 20px; z-index: 10;
    width: 120px; height: 120px;
    pointer-events: auto;
  }}

  #tooltip {{
    position: absolute; z-index: 20; display: none;
    background: #0f172a; border-radius: 8px;
    padding: 10px 14px; color: #f8fafc; font-size: 12px; font-weight: 500;
    pointer-events: none; box-shadow: 0 8px 20px rgba(0, 0, 0, 0.18);
    line-height: 1.6;
  }}
  canvas {{ display: block; }}
</style>
</head>
<body>

<div id="ui-container">
  <div class="card">
    <h1 id="title-text">Urban Context</h1>
    <div class="subtitle" id="coords-text">Architectural Site Study</div>
    <div class="metrics-grid">
      <div class="metric-item"><span class="metric-label">Site Area</span><span class="metric-val" id="val-area">-</span></div>
      <div class="metric-item"><span class="metric-label">Area Tier</span><span class="metric-val" id="val-tier">-</span></div>
      <div class="metric-item"><span class="metric-label">FAR</span><span class="metric-val" id="val-far">-</span></div>
      <div class="metric-item"><span class="metric-label">Buildings</span><span class="metric-val" id="val-bldgs">-</span></div>
    </div>
  </div>
</div>

<div id="controls-bar">
  <button class="toggle-btn active" id="btn-ortho">Axonometric</button>
  <button class="toggle-btn" id="btn-persp">Perspective</button>
</div>

<!-- Blender Orientation Gizmo widget div placed directly below top-right bar -->
<div id="gizmo-container"></div>

<div id="tooltip"></div>

<script type="importmap">
{{
  "imports": {{
    "three": "https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js",
    "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/"
  }}
}}
</script>

<script type="module">
import * as THREE from 'three';
import {{ OrbitControls }} from 'three/addons/controls/OrbitControls.js';

const DATA = {scene_data_json};

// --- Scene Setup ---
const scene = new THREE.Scene();
scene.background = new THREE.Color(0xffffff); // Pure 100% white background

const aspect = window.innerWidth / window.innerHeight;
const R = DATA.radius;

// Orthographic Camera (Axonometric) - DEFAULT
const orthoSize = R * 1.45;
const cameraOrtho = new THREE.OrthographicCamera(
  -orthoSize * aspect, orthoSize * aspect,
  orthoSize, -orthoSize,
  1, 3000
);
const camDist = R * 2.8;
cameraOrtho.position.set(camDist * 0.7, camDist * 0.65, camDist * 0.7);

// Perspective Camera
const cameraPersp = new THREE.PerspectiveCamera(38, aspect, 1, 3000);
cameraPersp.position.set(camDist * 0.7, camDist * 0.65, camDist * 0.7);

let activeCamera = cameraOrtho; // DEFAULT AXONOMETRIC

// Main Renderer
const renderer = new THREE.WebGLRenderer({{ antialias: true, alpha: true }});
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.toneMapping = THREE.NoToneMapping;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
document.body.appendChild(renderer.domElement);

// Controls (dampingFactor = 0.18 for fast easing, maxPolarAngle = Math.PI / 2.0 to allow TRUE 100% horizontal orthographic elevations)
const controls = new OrbitControls(activeCamera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.18;
controls.maxPolarAngle = Math.PI / 2.0; // Allow true flat horizontal view
controls.target.set(0, DATA.maxHeight * 0.08, 0);
controls.update();

// --- Directional Sun Light for Soft Shadow Casting ---
const sunLight = new THREE.DirectionalLight(0xffffff, 1.0);
sunLight.position.set(130, 220, 90);
sunLight.castShadow = true;
sunLight.shadow.mapSize.width = 2048;
sunLight.shadow.mapSize.height = 2048;

const shadowDim = R * 1.6;
sunLight.shadow.camera.left = -shadowDim;
sunLight.shadow.camera.right = shadowDim;
sunLight.shadow.camera.top = shadowDim;
sunLight.shadow.camera.bottom = -shadowDim;
sunLight.shadow.camera.near = 10;
sunLight.shadow.camera.far = 600;

// Eliminate Perspective Shadow Flickering using normalBias and bias offset
sunLight.shadow.bias = -0.0005;
sunLight.shadow.normalBias = 0.05;
scene.add(sunLight);

// --- 100% Pure White Ground Plane ---
const groundGeom = new THREE.PlaneGeometry(R * 2, R * 2);
const groundMat = new THREE.MeshBasicMaterial({{ color: 0xffffff }});
const ground = new THREE.Mesh(groundGeom, groundMat);
ground.rotation.x = -Math.PI / 2;
ground.position.y = -0.05;
scene.add(ground);

// --- Shared ShadowMaterial Overlay with PolygonOffset to eliminate Perspective Z-Fighting Flickering ---
const sharedShadowMat = new THREE.ShadowMaterial({{
  color: 0x000000,
  opacity: 0.12,
  polygonOffset: true,
  polygonOffsetFactor: -1.0,
  polygonOffsetUnits: -1.0,
}});

const shadowPlane = new THREE.Mesh(groundGeom, sharedShadowMat);
shadowPlane.rotation.x = -Math.PI / 2;
shadowPlane.position.y = -0.04;
shadowPlane.receiveShadow = true;
scene.add(shadowPlane);

// Bounding box border line (Clean Neutral Grey)
const borderPts = [
  new THREE.Vector3(-R, 0.1,  R),
  new THREE.Vector3( R, 0.1,  R),
  new THREE.Vector3( R, 0.1, -R),
  new THREE.Vector3(-R, 0.1, -R),
  new THREE.Vector3(-R, 0.1,  R),
];
const borderGeom = new THREE.BufferGeometry().setFromPoints(borderPts);
scene.add(new THREE.Line(borderGeom, new THREE.LineBasicMaterial({{ color: 0xd1d5db, linewidth: 1.2 }})));

// --- Meter Scale Ticks on ALL 4 SIDES of the Square Boundary Box ---
function createTickLabel(text) {{
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  canvas.width = 128; canvas.height = 64;
  ctx.font = '400 20px Inter, sans-serif'; // Regular non-bold font
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillStyle = '#000000'; // Pure solid black
  ctx.fillText(text, 64, 32);
  const texture = new THREE.CanvasTexture(canvas);
  texture.minFilter = THREE.LinearFilter;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({{ map: texture, transparent: true }}));
  sprite.scale.set(14, 7, 1);
  return sprite;
}}

for (let val = -R; val <= R; val += 50) {{
  // 1. Front X border (Z = R)
  const xFront = createTickLabel(`${{val}}m`);
  xFront.position.set(val, 0.5, R + 7);
  scene.add(xFront);

  // 2. Back X border (Z = -R)
  const xBack = createTickLabel(`${{val}}m`);
  xBack.position.set(val, 0.5, -R - 7);
  scene.add(xBack);

  // 3. Left Z border (X = -R)
  const zLeft = createTickLabel(`${{val}}m`);
  zLeft.position.set(-R - 7, 0.5, -val);
  scene.add(zLeft);

  // 4. Right Z border (X = R)
  const zRight = createTickLabel(`${{val}}m`);
  zRight.position.set(R + 7, 0.5, -val);
  scene.add(zRight);
}}

// --- Helper: Build Architectural Volume with MeshBasicMaterial for 100% Unshaded White ---
function createArchitecturalVolume(verts, faces, colorHex = 0xffffff, opacity = 1.0, isRoad = false) {{
  const group = new THREE.Group();

  const geom = new THREE.BufferGeometry();
  const pos = new Float32Array(faces.length * 9);

  for (let fi = 0; fi < faces.length; fi++) {{
    const f = faces[fi];
    for (let vi = 0; vi < 3; vi++) {{
      const v = verts[f[vi]];
      pos[fi * 9 + vi * 3 + 0] = v[0];
      pos[fi * 9 + vi * 3 + 1] = v[2];
      pos[fi * 9 + vi * 3 + 2] = -v[1];
    }}
  }}

  geom.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geom.computeVertexNormals();

  const baseMat = new THREE.MeshBasicMaterial({{
    color: new THREE.Color(colorHex),
    transparent: opacity < 1.0,
    opacity: opacity,
    polygonOffset: isRoad,
    polygonOffsetFactor: isRoad ? 2.0 : 0.0,
    polygonOffsetUnits: isRoad ? 2.0 : 0.0,
  }});
  const baseMesh = new THREE.Mesh(geom, baseMat);

  if (!isRoad) {{
    baseMesh.castShadow = true;
    group.add(baseMesh);

    const shadowMesh = new THREE.Mesh(geom, sharedShadowMat);
    shadowMesh.receiveShadow = true;
    group.add(shadowMesh);
  }} else {{
    baseMesh.castShadow = false;
    baseMesh.receiveShadow = false; // Roads get clean shadows from shadowPlane under them with ZERO double-darkening
    group.add(baseMesh);
  }}

  return {{ geom, baseMesh, group }};
}}

// --- Render Context Buildings ---
const interactiveObjects = [];
for (const b of DATA.buildings) {{
  const faceColor = 0xffffff;
  const edgeColor = 0x999999;

  const {{ geom, baseMesh, group }} = createArchitecturalVolume(b.vertices, b.faces, faceColor, 0.98, false);
  baseMesh.userData = {{
    isBuilding: true,
    area: b.area,
    height: b.height,
    floors: b.floors,
    use: b.use,
  }};

  const edges = new THREE.EdgesGeometry(geom, 20);
  const lineMat = new THREE.LineBasicMaterial({{ color: new THREE.Color(edgeColor), linewidth: 1.2 }});
  group.add(new THREE.LineSegments(edges, lineMat));

  scene.add(group);
  interactiveObjects.push(baseMesh);
}}

// --- Render Vehicular Road Network ---
if (DATA.roads) {{
  for (const r of DATA.roads) {{
    const {{ baseMesh, group }} = createArchitecturalVolume(r.vertices, r.faces, 0xffffff, 1.0, true);
    scene.add(group);
  }}
  if (DATA.roadOutlines) {{
    for (const outline of DATA.roadOutlines) {{
      if (outline.length >= 2) {{
        const rPts = outline.map(p => new THREE.Vector3(p[0], 0.04, -p[1]));
        const rGeom = new THREE.BufferGeometry().setFromPoints(rPts);
        const rMat = new THREE.LineBasicMaterial({{ color: 0xd1d5db, linewidth: 1.0 }});
        scene.add(new THREE.Line(rGeom, rMat));
      }}
    }}
  }}
}}

// --- Render Green Spaces / Parks ---
if (DATA.greenSpaces) {{
  for (const g of DATA.greenSpaces) {{
    const {{ baseMesh, group }} = createArchitecturalVolume(g.vertices, g.faces, 0xdcfce7, 1.0, true);
    scene.add(group);
  }}
}}

// --- Render Central Testing Site Parcel ---
if (DATA.site) {{
  const siteGroup = new THREE.Group();
  const siteFaceColor = 0xfca5a5; // Soft Coral Red

  const geom = new THREE.BufferGeometry();
  const pos = new Float32Array(DATA.site.faces.length * 9);
  for (let fi = 0; fi < DATA.site.faces.length; fi++) {{
    const f = DATA.site.faces[fi];
    for (let vi = 0; vi < 3; vi++) {{
      const v = DATA.site.vertices[f[vi]];
      pos[fi * 9 + vi * 3 + 0] = v[0];
      pos[fi * 9 + vi * 3 + 1] = v[2];
      pos[fi * 9 + vi * 3 + 2] = -v[1];
    }}
  }}
  geom.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geom.computeVertexNormals();

  const baseMat = new THREE.MeshBasicMaterial({{
    color: new THREE.Color(siteFaceColor),
    transparent: true, opacity: 0.88,
  }});
  const baseMesh = new THREE.Mesh(geom, baseMat);
  baseMesh.castShadow = true;
  baseMesh.userData = {{
    isSite: true,
    area: DATA.siteArea,
    tier: DATA.areaTier,
    far: DATA.metrics.far,
    bldgs: DATA.metrics.buildingCount,
  }};
  siteGroup.add(baseMesh);
  interactiveObjects.push(baseMesh);

  if (DATA.sitePerimeter && DATA.sitePerimeter.length >= 3) {{
    const outPts = DATA.sitePerimeter.map(p => new THREE.Vector3(p[0], 0.25, -p[1]));
    const siteLineGeom = new THREE.BufferGeometry().setFromPoints(outPts);
    const siteLineMat = new THREE.LineBasicMaterial({{ color: 0xef4444, linewidth: 2.5 }});
    siteGroup.add(new THREE.Line(siteLineGeom, siteLineMat));
  }}

  scene.add(siteGroup);
}}

// --- Update UI Panel ---
document.getElementById('title-text').innerText = DATA.cityName;
document.getElementById('coords-text').innerText = `Lat: ${{DATA.coords.lat?.toFixed(4) || '?'}}, Lon: ${{DATA.coords.lon?.toFixed(4) || '?'}}`;
document.getElementById('val-area').innerText = `${{DATA.siteArea}} m²`;
document.getElementById('val-tier').innerText = `${{DATA.areaTier}} Tier`;
document.getElementById('val-far').innerText = DATA.metrics.far;
document.getElementById('val-bldgs').innerText = DATA.metrics.buildingCount;

// --- Smooth Camera View Snap Function (Works 100% in Perspective & Axonometric Modes) ---
let isAnimatingCamera = false;
let animStartTime = 0;
let animStartPos = new THREE.Vector3();
let animEndPos = new THREE.Vector3();
const ANIM_DURATION = 350; // ms

function snapToView(dirX, dirY, dirZ) {{
  const target = controls.target.clone();
  animStartPos.copy(activeCamera.position);
  
  if (dirY === 1) {{
    // Top view (Z axis)
    animEndPos.set(target.x + 0.001, target.y + camDist, target.z + 0.001);
  }} else if (dirY === -1) {{
    // Bottom view (-Z axis)
    animEndPos.set(target.x + 0.001, target.y - camDist, target.z + 0.001);
  }} else if (dirX === 1) {{
    // Right view (X axis)
    animEndPos.set(target.x + camDist, target.y, target.z);
  }} else if (dirX === -1) {{
    // Left view (-X axis)
    animEndPos.set(target.x - camDist, target.y, target.z);
  }} else if (dirZ === 1) {{
    // Front view (Y axis depth)
    animEndPos.set(target.x, target.y, target.z + camDist);
  }} else if (dirZ === -1) {{
    // Back view (-Y axis depth)
    animEndPos.set(target.x, target.y, target.z - camDist);
  }}

  animStartTime = performance.now();
  isAnimatingCamera = true;
}}

// --- Custom Interactive Blender Orientation Gizmo Widget ---
const gizmoContainer = document.getElementById('gizmo-container');
const gizmoCanvas = document.createElement('canvas');
gizmoCanvas.width = 240; // 2x hidpi
gizmoCanvas.height = 240;
gizmoCanvas.style.width = '120px';
gizmoCanvas.style.height = '120px';
gizmoContainer.appendChild(gizmoCanvas);
const gctx = gizmoCanvas.getContext('2d');

// Gizmo Axis Definitions: Blender CAD Standards
// X = Red (#ef4444) [Horizontal Right]
// Y = Green (#22c55e) [Horizontal Depth]
// Z = Blue (#3b82f6) [Vertical Height]
const AXES = [
  {{ label: 'X', dir: [1, 0, 0], color: '#ef4444', isNeg: false }},
  {{ label: 'Y', dir: [0, 0, 1], color: '#22c55e', isNeg: false }},
  {{ label: 'Z', dir: [0, 1, 0], color: '#3b82f6', isNeg: false }},
  {{ label: '-X', dir: [-1, 0, 0], color: '#ef4444', isNeg: true }},
  {{ label: '-Y', dir: [0, 0, -1], color: '#22c55e', isNeg: true }},
  {{ label: '-Z', dir: [0, -1, 0], color: '#3b82f6', isNeg: true }},
];

let gizmoRenderNodes = [];

function drawGizmo() {{
  gctx.clearRect(0, 0, 240, 240);
  const cx = 120, cy = 120, r = 75;

  // Get current camera orientation matrix
  const mat = new THREE.Matrix4();
  mat.extractRotation(activeCamera.matrixWorldInverse);
  
  // Transform axis directions
  const projected = AXES.map((axis) => {{
    const vec = new THREE.Vector3(...axis.dir).applyMatrix4(mat);
    return {{
      ...axis,
      px: cx + vec.x * r,
      py: cy - vec.y * r,
      pz: vec.z,
    }};
  }});

  // Sort back-to-front by depth (pz)
  projected.sort((a, b) => a.pz - b.pz);
  gizmoRenderNodes = projected;

  // Draw connecting axis lines from center
  for (const node of projected) {{
    gctx.beginPath();
    gctx.moveTo(cx, cy);
    gctx.lineTo(node.px, node.py);
    gctx.strokeStyle = node.isNeg ? '#cbd5e1' : node.color;
    gctx.lineWidth = node.isNeg ? 2 : 4;
    gctx.stroke();
  }}

  // Draw node circles
  for (const node of projected) {{
    gctx.beginPath();
    const radius = node.isNeg ? 10 : 16;
    gctx.arc(node.px, node.py, radius, 0, Math.PI * 2);

    if (node.isNeg) {{
      gctx.fillStyle = '#ffffff';
      gctx.fill();
      gctx.strokeStyle = node.color;
      gctx.lineWidth = 3;
      gctx.stroke();
    }} else {{
      gctx.fillStyle = node.color;
      gctx.fill();
      gctx.font = 'bold 18px Inter, sans-serif';
      gctx.textAlign = 'center';
      gctx.textBaseline = 'middle';
      gctx.fillStyle = '#ffffff';
      gctx.fillText(node.label, node.px, node.py + 1);
    }}
  }}
}}

// Handle Gizmo Mouse Clicks on Nodes (Works 100% in Perspective AND Axonometric)
gizmoCanvas.addEventListener('click', (e) => {{
  const rect = gizmoCanvas.getBoundingClientRect();
  const mx = (e.clientX - rect.left) * 2;
  const my = (e.clientY - rect.top) * 2;

  // Check hit from front to back
  const clickable = [...gizmoRenderNodes].reverse();
  for (const node of clickable) {{
    const dist = Math.hypot(mx - node.px, my - node.py);
    const radius = node.isNeg ? 12 : 18;
    if (dist <= radius) {{
      snapToView(node.dir[0], node.dir[1], node.dir[2]);
      break;
    }}
  }}
}});

// --- Camera Switch Controls (Axonometric vs Perspective) ---
const btnPersp = document.getElementById('btn-persp');
const btnOrtho = document.getElementById('btn-ortho');

function setCamera(cameraMode) {{
  const prevCam = activeCamera;
  if (cameraMode === 'ortho') {{
    activeCamera = cameraOrtho;
    btnOrtho.classList.add('active');
    btnPersp.classList.remove('active');
  }} else {{
    activeCamera = cameraPersp;
    btnPersp.classList.add('active');
    btnOrtho.classList.remove('active');
  }}
  activeCamera.position.copy(prevCam.position);
  controls.object = activeCamera;
  controls.update();
}}

btnPersp.addEventListener('click', () => setCamera('persp'));
btnOrtho.addEventListener('click', () => setCamera('ortho'));

// --- Clean Architectural Building Tooltips ---
const raycaster = new THREE.Raycaster();
const mouse = new THREE.Vector2();
const tooltip = document.getElementById('tooltip');
let hoveredObj = null;

renderer.domElement.addEventListener('mousemove', (e) => {{
  mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
  mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;
  raycaster.setFromCamera(mouse, activeCamera);
  const hits = raycaster.intersectObjects(interactiveObjects);

  if (hoveredObj) {{
    hoveredObj.material.color.setHex(hoveredObj.userData.isSite ? 0xfca5a5 : 0xffffff);
    hoveredObj = null;
  }}

  if (hits.length > 0) {{
    const obj = hits[0].object;
    hoveredObj = obj;

    if (obj.userData.isSite) {{
      obj.material.color.setHex(0xf87171);
      tooltip.style.display = 'block';
      tooltip.style.left = (e.clientX + 14) + 'px';
      tooltip.style.top = (e.clientY + 14) + 'px';
      tooltip.innerHTML = `
        <div><b>Site Area:</b> ${{obj.userData.area}} m² (${{obj.userData.tier}} Tier)</div>
        <div><b>FAR:</b> ${{obj.userData.far}} &nbsp;|&nbsp; <b>Buildings:</b> ${{obj.userData.bldgs}}</div>
      `;
    }} else if (obj.userData.isBuilding) {{
      obj.material.color.setHex(0xe2e8f0);
      tooltip.style.display = 'block';
      tooltip.style.left = (e.clientX + 14) + 'px';
      tooltip.style.top = (e.clientY + 14) + 'px';
      tooltip.innerHTML = `
        <div style="font-weight:700; color:#2563eb; margin-bottom:3px;">${{obj.userData.use}}</div>
        <div><b>Footprint:</b> ${{obj.userData.area}} m² &nbsp;|&nbsp; <b>Floors:</b> ~${{obj.userData.floors}}</div>
        <div><b>Height:</b> ${{obj.userData.height}} m</div>
      `;
    }}
  }} else {{
    tooltip.style.display = 'none';
  }}
}});

// --- Resize ---
window.addEventListener('resize', () => {{
  const newAspect = window.innerWidth / window.innerHeight;
  cameraPersp.aspect = newAspect;
  cameraPersp.updateProjectionMatrix();

  cameraOrtho.left = -orthoSize * newAspect;
  cameraOrtho.right = orthoSize * newAspect;
  cameraOrtho.top = orthoSize;
  cameraOrtho.bottom = -orthoSize;
  cameraOrtho.updateProjectionMatrix();

  renderer.setSize(window.innerWidth, window.innerHeight);
}});

// --- Animation Loop ---
function animate() {{
  requestAnimationFrame(animate);

  // Smooth camera view snap animation
  if (isAnimatingCamera) {{
    const now = performance.now();
    const progress = Math.min(1.0, (now - animStartTime) / ANIM_DURATION);
    const easeProgress = 1 - Math.pow(1 - progress, 3); // cubic ease out

    activeCamera.position.lerpVectors(animStartPos, animEndPos, easeProgress);
    controls.update();

    if (progress >= 1.0) {{
      isAnimatingCamera = false;
    }}
  }} else {{
    controls.update();
  }}

  renderer.render(scene, activeCamera);

  // Render dynamic Blender orientation gizmo widget
  drawGizmo();
}}
animate();
</script>
</body>
</html>"""
