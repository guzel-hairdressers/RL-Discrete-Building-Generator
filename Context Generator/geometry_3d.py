"""
3D Geometry Engine and Urban Metric Computations for Context Generator.
Enforces strict Counter-Clockwise (CCW) polygon orientation and outward face normals to fix backface rendering bugs.
Computes true District FAR (Total Floor Area / Total District Area).
"""

import math
import numpy as np

try:
    from shapely.geometry import Polygon, MultiPolygon, Point
    from shapely.geometry.polygon import orient
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False


def latlon_to_local_meters(lat, lon, ref_lat, ref_lon):
    """Convert (lat, lon) coordinates to local tangent plane meters relative to ref origin."""
    r_earth = 6371000.0
    d_lat = math.radians(lat - ref_lat)
    d_lon = math.radians(lon - ref_lon)
    x = d_lon * r_earth * math.cos(math.radians(ref_lat))
    y = d_lat * r_earth
    return x, y


def local_meters_to_latlon(x, y, ref_lat, ref_lon):
    """Convert local tangent plane meters (x, y) back to WGS84 (lat, lon)."""
    r_earth = 6371000.0
    d_lat = math.degrees(y / r_earth)
    d_lon = math.degrees(x / (r_earth * math.cos(math.radians(ref_lat))))
    return ref_lat + d_lat, ref_lon + d_lon


def ensure_ccw_polygon(verts_2d):
    """
    Ensures a 2D polygon vertex array is in strict Counter-Clockwise (CCW) order
    so that extruded side wall normals ALWAYS point OUTWARDS.
    """
    if len(verts_2d) < 3:
        return verts_2d

    if np.allclose(verts_2d[0], verts_2d[-1]):
        clean_verts = verts_2d[:-1]
    else:
        clean_verts = verts_2d

    if SHAPELY_AVAILABLE:
        try:
            poly = Polygon(clean_verts)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if isinstance(poly, Polygon):
                ccw_poly = orient(poly, sign=1.0)
                coords = list(ccw_poly.exterior.coords)[:-1]
                return [[round(x, 2), round(y, 2)] for x, y in coords]
        except Exception:
            pass

    arr = np.array(clean_verts)
    x, y = arr[:, 0], arr[:, 1]
    signed_area = 0.5 * np.sum(x * np.roll(y, -1) - y * np.roll(x, -1))
    if signed_area < 0:
        return clean_verts[::-1]
    return clean_verts


def latlon_to_local_meters(lat, lon, ref_lat, ref_lon):
    R = 6378137.0
    d_lat = math.radians(lat - ref_lat)
    d_lon = math.radians(lon - ref_lon)
    ref_lat_rad = math.radians(ref_lat)
    x = d_lon * math.cos(ref_lat_rad) * R
    y = d_lat * R
    return x, y


def extrude_polygon_to_3d_mesh(vertices_2d, height, base_z=0.0):
    verts_ccw = ensure_ccw_polygon(vertices_2d)
    n = len(verts_ccw)
    if n < 3:
        return None

    verts_3d = []
    for x, y in verts_ccw:
        verts_3d.append([x, y, base_z])
    for x, y in verts_ccw:
        verts_3d.append([x, y, base_z + height])

    verts_3d = np.array(verts_3d, dtype=np.float64)
    faces = []

    for i in range(n):
        next_i = (i + 1) % n
        b1 = i
        b2 = next_i
        t1 = i + n
        t2 = next_i + n

        faces.append([b1, b2, t2])
        faces.append([b1, t2, t1])

    for i in range(1, n - 1):
        faces.append([0, i + 1, i])

    for i in range(1, n - 1):
        faces.append([n, n + i, n + i + 1])

    faces = np.array(faces, dtype=np.int32)

    return {
        "vertices": verts_3d,
        "faces": faces,
        "height": height,
        "base_z": base_z,
        "centroid": np.mean(verts_3d, axis=0).tolist(),
    }


def compute_quick_metrics(buildings, radius_m=100.0):
    """
    Computes quick metrics (far, gcr, building_count, max_height, avg_height) for batch evaluation.
    """
    if not buildings:
        return {"far": 0.0, "gcr": 0.0, "building_count": 0, "max_height": 0.0, "avg_height": 0.0}

    total_fp = 0.0
    total_floor = 0.0
    heights = []

    for b in buildings:
        h = max(4.0, float(b.get("height", 30.0)))
        heights.append(h)
        floors = max(1, round(h / 3.5))

        verts = b.get("vertices_2d", [])
        if len(verts) >= 3:
            arr = np.array(verts)
            x, y = arr[:, 0], arr[:, 1]
            fp_area = 0.5 * np.abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))
            total_fp += fp_area
            total_floor += fp_area * floors

    # Context bounding box / district area = (2 * radius)^2
    box_area = (2.0 * radius_m) ** 2

    gcr = round(total_fp / box_area, 3) if box_area > 0 else 0.0
    far = round(total_floor / box_area, 2) if box_area > 0 else 0.0

    return {
        "far": far,
        "gcr": gcr,
        "building_count": len(buildings),
        "max_height": round(float(np.max(heights)), 1) if heights else 0.0,
        "avg_height": round(float(np.mean(heights)), 1) if heights else 0.0,
    }


def compute_urban_metrics(site_poly_2d, context_buildings, radius_m=160.0):
    """
    Computes urban planning spatial & environmental metrics:
    - Site Area (m²)
    - Total Context Footprint Area (m²)
    - District Ground Coverage Ratio (GCR) = Total Footprint Area / District Area (π R²)
    - District Floor Area Ratio (FAR) = Total Floor Area / District Area (π R²)
    - Sky View Factor (SVF) proxy
    """
    if SHAPELY_AVAILABLE and isinstance(site_poly_2d, (Polygon, MultiPolygon)):
        site_area = site_poly_2d.area
        site_centroid = (site_poly_2d.centroid.x, site_poly_2d.centroid.y)
    else:
        site_verts = np.array(site_poly_2d)
        x, y = site_verts[:, 0], site_verts[:, 1]
        site_area = 0.5 * np.abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))
        site_centroid = (float(np.mean(x)), float(np.mean(y)))

    total_footprint_area = 0.0
    total_floor_area = 0.0
    heights = []

    for b in context_buildings:
        h = b.get("height", 15.0)
        heights.append(h)
        floors = max(1, int(h / 3.8))

        verts = np.array(b["vertices_2d"])
        x, y = verts[:, 0], verts[:, 1]
        fp_area = 0.5 * np.abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))

        total_footprint_area += fp_area
        total_floor_area += fp_area * floors

    district_area_m2 = math.pi * (radius_m ** 2)
    
    district_gcr = total_footprint_area / district_area_m2 if district_area_m2 > 0 else 0.0
    district_far = total_floor_area / district_area_m2 if district_area_m2 > 0 else 0.0

    svf = calculate_svf_proxy(site_centroid, context_buildings, num_rays=36)

    return {
        "site_area_m2": round(site_area, 2),
        "district_area_m2": round(district_area_m2, 2),
        "building_count": len(context_buildings),
        "total_footprint_area_m2": round(total_footprint_area, 2),
        "total_floor_area_m2": round(total_floor_area, 2),
        "ground_coverage_ratio": round(district_gcr, 3),
        "floor_area_ratio": round(district_far, 2),
        "avg_height_m": round(float(np.mean(heights)), 2) if heights else 0.0,
        "max_height_m": round(float(np.max(heights)), 2) if heights else 0.0,
        "min_height_m": round(float(np.min(heights)), 2) if heights else 0.0,
        "sky_view_factor": round(svf, 3),
    }


def calculate_svf_proxy(origin_2d, context_buildings, num_rays=36):
    ox, oy = origin_2d
    max_angles = np.zeros(num_rays)

    for b in context_buildings:
        h = b.get("height", 15.0) - 1.5
        if h <= 0:
            continue

        verts = np.array(b["vertices_2d"])
        for vx, vy in verts:
            dx = vx - ox
            dy = vy - oy
            dist = math.hypot(dx, dy)
            if dist < 1.0:
                continue

            elevation = math.atan2(h, dist)
            azimuth = (math.atan2(dy, dx) + 2 * math.pi) % (2 * math.pi)

            ray_idx = int(azimuth / (2 * math.pi / num_rays)) % num_rays
            if elevation > max_angles[ray_idx]:
                max_angles[ray_idx] = elevation

    svf = np.mean(np.cos(max_angles) ** 2)
    return float(svf)
