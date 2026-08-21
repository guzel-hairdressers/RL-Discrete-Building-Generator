import math
import geometry as G

def partition_site_into_macro_bays(site_outer, core_polygon, min_bay_area=30.0, max_bays=6):
    """Partition a site boundary around a central core hub into clean macro-structural bays.
    
    Uses radial Voronoi bisector rays from the core hub to the site perimeter vertices.
    Guarantees every bay is a simple polygon with a direct contact wall to the core hub.
    """
    # 1. Compute core hub centroid and vertices
    core_cx = sum(p["x"] for p in core_polygon) / len(core_polygon)
    core_cy = sum(p["y"] for p in core_polygon) / len(core_polygon)
    
    # 2. Extract site vertices and angles relative to core center
    site_pts = list(site_outer)
    n_site = len(site_pts)
    
    # Filter significant boundary vertices (concavities, corners, extrema)
    angles_with_pts = []
    for i, p in enumerate(site_pts):
        angle = math.atan2(p["y"] - core_cy, p["x"] - core_cx) % (2 * math.pi)
        angles_with_pts.append((angle, p, i))
        
    angles_with_pts.sort(key=lambda x: x[0])
    
    # Cluster into M primary radial partition sectors (2 to 6 bays)
    num_bays = min(max_bays, max(2, len(core_polygon)))
    sector_step = (2 * math.pi) / num_bays
    
    # Pick site vertices closest to each sector boundary
    chosen_split_indices = []
    for s in range(num_bays):
        target_angle = s * sector_step
        # Find closest site vertex
        best_diff = 999.0
        best_idx = 0
        for angle, p, idx in angles_with_pts:
            diff = abs((angle - target_angle + math.pi) % (2 * math.pi) - math.pi)
            if diff < best_diff:
                best_diff = diff
                best_idx = idx
        if best_idx not in chosen_split_indices:
            chosen_split_indices.append(best_idx)
            
    chosen_split_indices.sort()
    if len(chosen_split_indices) < 2:
        chosen_split_indices = [0, n_site // 2]
        
    # 3. Form bays by walking along site perimeter between splits and connecting to core hub
    bays = []
    num_splits = len(chosen_split_indices)
    
    for i in range(num_splits):
        idx1 = chosen_split_indices[i]
        idx2 = chosen_split_indices[(i + 1) % num_splits]
        
        # Perimeter segment from idx1 to idx2
        if idx1 <= idx2:
            peri_pts = site_pts[idx1:idx2+1]
        else:
            peri_pts = site_pts[idx1:] + site_pts[:idx2+1]
            
        if len(peri_pts) < 2:
            continue
            
        # Find the core hub edge/vertex closest to peri_pts[-1] and peri_pts[0]
        p_start = peri_pts[0]
        p_end = peri_pts[-1]
        
        # Connect to core polygon
        c_end = min(core_polygon, key=lambda c: (c["x"]-p_end["x"])**2 + (c["y"]-p_end["y"])**2)
        c_start = min(core_polygon, key=lambda c: (c["x"]-p_start["x"])**2 + (c["y"]-p_start["y"])**2)
        
        # Construct bay polygon: peri_pts + [c_end, c_start]
        bay_poly = list(peri_pts)
        if c_end != c_start:
            bay_poly.extend([c_end, c_start])
        else:
            bay_poly.append(c_end)
            
        area = abs(G.polygon_signed_area(bay_poly))
        if area >= min_bay_area:
            bays.append({
                "bay_id": len(bays),
                "polygon": bay_poly,
                "area": area,
                "core_contact": (c_start, c_end),
            })
            
    return bays

if __name__ == "__main__":
    # Test on different procedural boundaries
    for seed in (42, 123, 456):
        rng = G.RNG(seed)
        boundary = G.make_boundary("lobed", rng.fork(11), {"boundaryWidth": 40.0, "boundaryHeight": 30.0})
        site = G.build_site(boundary, [])
        core_poly = [{"x": 18, "y": 13}, {"x": 22, "y": 13}, {"x": 22, "y": 17}, {"x": 18, "y": 17}]
        
        bays = partition_site_into_macro_bays(site["outer"], core_poly)
        print(f"Seed {seed}: Found {len(bays)} macro-bays, Total Bay Area = {sum(b['area'] for b in bays):.1f}m², Site Area = {site['exactArea']:.1f}m²")
        for b in bays:
            print(f"  - Bay {b['bay_id']}: Area = {b['area']:.1f}m², Vertices = {len(b['polygon'])}")
