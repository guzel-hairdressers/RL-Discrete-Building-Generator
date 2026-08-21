import math
import geometry as G

def rasterize_bay_to_grid(bay_polygon, grid_size=3.0):
    """Rasterize a bay polygon into a 2D discrete cell grid (3.0m pitch)."""
    xs = [p["x"] for p in bay_polygon]
    ys = [p["y"] for p in bay_polygon]
    min_x = math.floor(min(xs) / grid_size) * grid_size
    max_x = math.ceil(max(xs) / grid_size) * grid_size
    min_y = math.floor(min(ys) / grid_size) * grid_size
    max_y = math.ceil(max(ys) / grid_size) * grid_size
    
    cols = int(round((max_x - min_x) / grid_size))
    rows = int(round((max_y - min_y) / grid_size))
    
    grid = [[0 for _ in range(cols)] for _ in range(rows)]
    
    for r in range(rows):
        for c in range(cols):
            cell_cx = min_x + (c + 0.5) * grid_size
            cell_cy = min_y + (r + 0.5) * grid_size
            # Check if cell center is inside bay polygon
            if G.point_in_polygon({"x": cell_cx, "y": cell_cy}, bay_polygon):
                grid[r][c] = 1 # Valid cell inside bay
                
    return grid, min_x, min_y, cols, rows

def tessellate_grid_wfc(grid, min_x, min_y, grid_size=3.0):
    """Greedy WFC / Constraint Satisfaction Tiling on a rasterized bay grid."""
    rows = len(grid)
    cols = len(grid[0]) if rows > 0 else 0
    occupied = [[0 for _ in range(cols)] for _ in range(rows)]
    
    # Shapes in cell offsets: (name, [(dr, dc), ...], category)
    SHAPES = [
        ("quad-large", [(0,0), (0,1), (1,0), (1,1)], "room"),      # 2x2 cells (6x6m = 36m²)
        ("rect-wide",  [(0,0), (0,1), (0,2)],         "room"),      # 1x3 cells (3x9m = 27m²)
        ("rect-medium",[(0,0), (0,1)],                "room"),      # 1x2 cells (3x6m = 18m²)
        ("rect-vert",  [(0,0), (1,0)],                "room"),      # 2x1 cells (6x3m = 18m²)
        ("l-shape",    [(0,0), (1,0), (1,1)],         "special"),   # L-shape 3 cells (27m²)
        ("quad-small", [(0,0)],                       "room"),      # 1x1 cell  (3x3m = 9m²)
    ]
    
    placements = []
    
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == 1 and occupied[r][c] == 0:
                # Try placing largest matching shape
                placed = False
                for shape_name, offsets, cat in SHAPES:
                    # Check if all offsets fit and are valid & unoccupied
                    can_fit = True
                    for dr, dc in offsets:
                        nr, nc = r + dr, c + dc
                        if nr >= rows or nc >= cols or grid[nr][nc] == 0 or occupied[nr][nc] != 0:
                            can_fit = False
                            break
                    if can_fit:
                        # Place shape
                        for dr, dc in offsets:
                            occupied[r + dr][c + dc] = len(placements) + 1
                            
                        # Compute world polygon for this room
                        room_cells = [(min_x + (c + dc) * grid_size, min_y + (r + dr) * grid_size) for dr, dc in offsets]
                        # Polygon bounding box or footprint
                        min_cx = min(x for x, y in room_cells)
                        max_cx = max(x + grid_size for x, y in room_cells)
                        min_cy = min(y for x, y in room_cells)
                        max_cy = max(y + grid_size for x, y in room_cells)
                        
                        room_poly = [
                            {"x": min_cx, "y": min_cy},
                            {"x": max_cx, "y": min_cy},
                            {"x": max_cx, "y": max_cy},
                            {"x": min_cx, "y": max_cy},
                        ]
                        
                        placements.append({
                            "shape": shape_name,
                            "category": cat,
                            "polygon": room_poly,
                            "area": len(offsets) * grid_size * grid_size,
                            "cells_count": len(offsets),
                        })
                        placed = True
                        break
                        
    # Calculate packing fill ratio inside valid cells
    total_valid_cells = sum(sum(row) for row in grid)
    total_packed_cells = sum(p["cells_count"] for p in placements)
    pack_ratio = total_packed_cells / max(1, total_valid_cells)
    
    return placements, pack_ratio

if __name__ == "__main__":
    for seed in (42, 100, 202):
        rng = G.RNG(seed)
        boundary = G.make_boundary("lobed", rng.fork(11), {"boundaryWidth": 40.0, "boundaryHeight": 30.0})
        site = G.build_site(boundary, [])
        core_poly = [{"x": 18, "y": 13}, {"x": 22, "y": 13}, {"x": 22, "y": 17}, {"x": 18, "y": 17}]
        bays = G.partition_site_into_macro_bays(site["outer"], core_poly)
        
        print(f"\n--- SEED {seed} ---")
        total_rooms = 0
        for bay in bays:
            grid, min_x, min_y, cols, rows = rasterize_bay_to_grid(bay["polygon"])
            placements, pack_ratio = tessellate_grid_wfc(grid, min_x, min_y)
            total_rooms += len(placements)
            print(f"  Bay {bay['bay_id']} ({cols}x{rows} grid): {len(placements)} rooms placed, Pack Ratio = {pack_ratio*100:.1f}%")
        print(f"Total Rooms Generated: {total_rooms}")
