from __future__ import annotations

import math
from dataclasses import dataclass
from collections import Counter, defaultdict
from typing import Sequence, Any
import geometry as G

# ─────────────────────────────────────────────────────────
# Port infrastructure (used by the wall/rendering system)
# ─────────────────────────────────────────────────────────

@dataclass
class Port:
    shape_id: str       # ID of the placement
    edge_index: int     # index of the edge in the original polygon (0 to len(poly)-1)
    half: str           # "L" or "R"
    start: dict         # {"x": float, "y": float}
    end: dict           # {"x": float, "y": float}

@dataclass
class PortConnection:
    port_a: Port
    port_b: Port
    overlap_segment: tuple[dict, dict] | None = None

@dataclass
class LayoutGraph:
    nodes: dict[str, dict]            # shape_id -> placement dict
    connections: list[PortConnection] # list of port-to-port connections (for wall rendering)
    playground_id: int

# ─────────────────────────────────────────────────────────
# BPE merge infrastructure (full-edge adjacency)
# ─────────────────────────────────────────────────────────

@dataclass
class EdgeConnection:
    """A full-edge adjacency between two shapes sharing a collinear boundary."""
    shape_id_a: str
    shape_id_b: str
    edge_idx_a: int         # edge index on shape A's polygon
    edge_idx_b: int         # edge index on shape B's polygon
    overlap_start: dict     # {"x": float, "y": float} — start of overlap segment
    overlap_end: dict       # {"x": float, "y": float} — end of overlap segment
    overlap_fraction_a: float  # fraction of edge A that is overlapped
    overlap_fraction_b: float  # fraction of edge B that is overlapped

@dataclass(frozen=True)
class MergePairKey:
    """Canonical rotation-invariant key for a pair of adjacent shapes."""
    type_a: str          # e.g., "s3", "Q_rect_M"
    type_b: str          # e.g., "s3", "Q_rect_S"
    canon_edge_a: int    # canonicalized edge index on A (after symmetry normalization)
    canon_edge_b: int    # canonicalized edge index on B (after symmetry normalization)
    relative_angle: int  # relative angle between A and B, in degrees (snapped to 15°)

@dataclass
class MergedModule:
    type_id: str
    name: str
    poly: list[dict]
    components: list[dict] # list of basic shapes that make it up

# ─────────────────────────────────────────────────────────
# Utility functions
# ─────────────────────────────────────────────────────────

def distance(p1: dict, p2: dict) -> float:
    return math.hypot(p2["x"] - p1["x"], p2["y"] - p1["y"])

def _edge_length(poly: list[dict], edge_idx: int) -> float:
    """Length of edge from vertex edge_idx to vertex (edge_idx+1) % n."""
    p1 = poly[edge_idx]
    p2 = poly[(edge_idx + 1) % len(poly)]
    return math.hypot(p2["x"] - p1["x"], p2["y"] - p1["y"])

def _all_edge_lengths(poly: list[dict]) -> list[float]:
    """Compute all edge lengths for a polygon."""
    n = len(poly)
    return [math.hypot(
        poly[(i + 1) % n]["x"] - poly[i]["x"],
        poly[(i + 1) % n]["y"] - poly[i]["y"]
    ) for i in range(n)]

def _segments_collinear(first: dict, second: dict, third: dict, fourth: dict, tolerance: float = 1e-2) -> bool:
    first_length = distance(first, second)
    second_length = distance(third, fourth)
    if first_length <= 1e-5 or second_length <= 1e-5:
        return False
        
    dx1 = second["x"] - first["x"]
    dy1 = second["y"] - first["y"]
    dx2 = fourth["x"] - third["x"]
    dy2 = fourth["y"] - third["y"]
    
    direction_cross = abs(dx1 * dy2 - dy1 * dx2)
    if direction_cross > tolerance * first_length * second_length:
        return False
        
    def orient(p, q, r):
        return (q["x"] - p["x"]) * (r["y"] - p["y"]) - (q["y"] - p["y"]) * (r["x"] - p["x"])
        
    return (
        abs(orient(first, second, third)) <= tolerance * first_length
        and abs(orient(first, second, fourth)) <= tolerance * first_length
        and abs(orient(third, fourth, first)) <= tolerance * second_length
        and abs(orient(third, fourth, second)) <= tolerance * second_length
    )

def _overlap_interval_on_first(first: dict, second: dict, third: dict, fourth: dict, tolerance: float = 1e-2) -> tuple[float, float] | None:
    if not _segments_collinear(first, second, third, fourth, tolerance):
        return None
    dx = second["x"] - first["x"]
    dy = second["y"] - first["y"]
    length_squared = dx * dx + dy * dy
    if length_squared <= 1e-10:
        return None
    third_parameter = ((third["x"] - first["x"]) * dx + (third["y"] - first["y"]) * dy) / length_squared
    fourth_parameter = ((fourth["x"] - first["x"]) * dx + (fourth["y"] - first["y"]) * dy) / length_squared
    start = max(0.0, min(third_parameter, fourth_parameter))
    end = min(1.0, max(third_parameter, fourth_parameter))
    if (end - start) * math.sqrt(length_squared) <= tolerance:
        return None
    return (start, end)

# ─────────────────────────────────────────────────────────
# Port assignment (for wall/rendering system — unchanged)
# ─────────────────────────────────────────────────────────

def assign_ports(placement: dict) -> list[Port]:
    """Split each edge of the original placement polygon in half to create ports."""
    poly = placement["poly"]
    ports = []
    n = len(poly)
    for i in range(n):
        p1 = poly[i]
        p2 = poly[(i + 1) % n]
        mid = {
            "x": (p1["x"] + p2["x"]) / 2.0,
            "y": (p1["y"] + p2["y"]) / 2.0
        }
        # Port L goes from start to midpoint
        ports.append(Port(
            shape_id=placement["id"],
            edge_index=i,
            half="L",
            start=p1,
            end=mid
        ))
        # Port R goes from midpoint to end
        ports.append(Port(
            shape_id=placement["id"],
            edge_index=i,
            half="R",
            start=mid,
            end=p2
        ))
    return ports

# ─────────────────────────────────────────────────────────
# Layout graph extraction (port-based, for wall rendering)
# ─────────────────────────────────────────────────────────

def extract_layout_graph(placements: list[dict], playground_id: int = 0) -> LayoutGraph:
    """Build the adjacency graph of placements on a floor using port-to-port connections."""
    nodes = {p["id"]: p for p in placements}
    connections = []
    
    # 1. Assign ports for all placements
    all_ports = {}
    for pid, p in nodes.items():
        all_ports[pid] = assign_ports(p)
        
    # 2. Check for port overlaps between every pair of placements
    pids = list(nodes.keys())
    n_placements = len(pids)
    for i in range(n_placements):
        pid_a = pids[i]
        ports_a = all_ports[pid_a]
        for j in range(i + 1, n_placements):
            pid_b = pids[j]
            ports_b = all_ports[pid_b]
            
            for pa in ports_a:
                for pb in ports_b:
                    # Check if port segments A and B are collinear and overlap
                    # Since ports are directed (start -> end), anti-parallel ports connect.
                    # We check if segment A (pa.start -> pa.end) overlaps with segment B (pb.end -> pb.start)
                    overlap = G._overlap_interval_on_first(
                        pa.start, pa.end, pb.end, pb.start
                    )
                    if overlap is not None:
                        start, end = overlap
                        overlap_len = end - start
                        # If they share at least 90% of the port length, count as connected
                        if overlap_len >= 0.90:
                            dx = pa.end["x"] - pa.start["x"]
                            dy = pa.end["y"] - pa.start["y"]
                            overlap_start = {
                                "x": pa.start["x"] + start * dx,
                                "y": pa.start["y"] + start * dy
                            }
                            overlap_end = {
                                "x": pa.start["x"] + end * dx,
                                "y": pa.start["y"] + end * dy
                            }
                            connections.append(PortConnection(
                                port_a=pa,
                                port_b=pb,
                                overlap_segment=(overlap_start, overlap_end)
                            ))
                            
    return LayoutGraph(nodes=nodes, connections=connections, playground_id=playground_id)

# ─────────────────────────────────────────────────────────
# Shape type extraction
# ─────────────────────────────────────────────────────────

def get_node_shape_type(node: dict) -> str:
    """Safely extract the canonical shape type ID from a node, stripping instance suffixes."""
    shape_type = node.get("shapeType")
    if shape_type:
        return shape_type
    module_id = node.get("moduleId", "")
    if not module_id:
        return node["id"]
    parts = str(module_id).split("-")
    if "procedural" in parts:
        try:
            idx = parts.index("procedural")
            if idx + 1 < len(parts):
                return parts[idx + 1]
        except ValueError:
            pass
    # The first part is the shape type (e.g. T_equi, s3, Q_rect_S)
    return parts[0]

# ─────────────────────────────────────────────────────────
# Full-edge adjacency detection (for BPE merging)
# ─────────────────────────────────────────────────────────

def find_edge_connections(graph: LayoutGraph) -> list[EdgeConnection]:
    """Find all full-edge adjacencies between shapes in a layout graph.
    
    For each pair of shapes, check every edge-pair for collinear overlap.
    An edge connection is recorded when two edges from different shapes overlap
    by at least 40% of the shorter edge's length. This is much more robust than
    the half-edge port system since it checks the entire edge, not just halves.
    """
    connections = []
    pids = list(graph.nodes.keys())
    n = len(pids)
    
    for i in range(n):
        pid_a = pids[i]
        node_a = graph.nodes[pid_a]
        poly_a = node_a["poly"]
        n_a = len(poly_a)
        
        for j in range(i + 1, n):
            pid_b = pids[j]
            node_b = graph.nodes[pid_b]
            poly_b = node_b["poly"]
            n_b = len(poly_b)
            
            # Find the best overlapping edge pair between A and B
            best_conn = None
            best_overlap_len = 0.0
            
            for ea in range(n_a):
                a1 = poly_a[ea]
                a2 = poly_a[(ea + 1) % n_a]
                len_a = distance(a1, a2)
                if len_a < 1e-5:
                    continue
                    
                for eb in range(n_b):
                    b1 = poly_b[eb]
                    b2 = poly_b[(eb + 1) % n_b]
                    len_b = distance(b1, b2)
                    if len_b < 1e-5:
                        continue
                    
                    overlap = _overlap_interval_on_first(a1, a2, b2, b1)
                    if overlap is None:
                        # Also try parallel direction in case winding is same
                        overlap = _overlap_interval_on_first(a1, a2, b1, b2)
                    
                    if overlap is not None:
                        t_start, t_end = overlap
                        overlap_abs_len = (t_end - t_start) * len_a
                        min_edge_len = min(len_a, len_b)
                        
                        # Require at least 40% of the shorter edge to overlap
                        if overlap_abs_len >= 0.40 * min_edge_len and overlap_abs_len > best_overlap_len:
                            dx = a2["x"] - a1["x"]
                            dy = a2["y"] - a1["y"]
                            ov_start = {
                                "x": a1["x"] + t_start * dx,
                                "y": a1["y"] + t_start * dy
                            }
                            ov_end = {
                                "x": a1["x"] + t_end * dx,
                                "y": a1["y"] + t_end * dy
                            }
                            
                            # Also compute overlap fraction on edge B
                            overlap_b = _overlap_interval_on_first(b1, b2, a1, a2)
                            frac_b = 0.0
                            if overlap_b is not None:
                                frac_b = overlap_b[1] - overlap_b[0]
                            else:
                                frac_b = overlap_abs_len / len_b
                            
                            best_conn = EdgeConnection(
                                shape_id_a=pid_a,
                                shape_id_b=pid_b,
                                edge_idx_a=ea,
                                edge_idx_b=eb,
                                overlap_start=ov_start,
                                overlap_end=ov_end,
                                overlap_fraction_a=t_end - t_start,
                                overlap_fraction_b=frac_b,
                            )
                            best_overlap_len = overlap_abs_len
            
            if best_conn is not None:
                connections.append(best_conn)
    
    return connections

# ─────────────────────────────────────────────────────────
# Geometric symmetry canonicalization (edge-level)
# ─────────────────────────────────────────────────────────

def canonicalize_edge_index(poly: list[dict], edge_index: int) -> int:
    """Normalize edge index for shapes with rotational symmetry.
    
    - Equilateral triangles (3 equal sides): all edges → 0
    - Squares & Rhombuses (4 equal sides): all edges → 0
    - Parallelograms/rectangles (4 sides, opposite equal): edge 2 → 0, edge 3 → 1
    - All other shapes (including Isosceles Triangles): edge index unchanged
    """
    if not poly or len(poly) < 3:
        return edge_index
    
    n = len(poly)
    lengths = _all_edge_lengths(poly)
    
    # Equilateral triangles: 3 equal sides
    if n == 3:
        if abs(lengths[0] - lengths[1]) < 1e-2 and abs(lengths[1] - lengths[2]) < 1e-2:
            return 0
    
    # Quads (n == 4):
    elif n == 4:
        # Squares & Rhombuses: all 4 sides equal -> all map to 0
        if (
            abs(lengths[0] - lengths[1]) < 1e-2
            and abs(lengths[1] - lengths[2]) < 1e-2
            and abs(lengths[2] - lengths[3]) < 1e-2
        ):
            return 0
        # Parallelograms/rectangles: opposite sides equal -> edge 2 -> 0, edge 3 → 1
        elif abs(lengths[0] - lengths[2]) < 1e-2 and abs(lengths[1] - lengths[3]) < 1e-2:
            if edge_index == 2:
                return 0
            elif edge_index == 3:
                return 1
    
    return edge_index

def canonicalize_merge_key(conn: EdgeConnection, graph: LayoutGraph) -> MergePairKey:
    """Create a canonical rotation-invariant merge key for an edge connection."""
    node_a = graph.nodes[conn.shape_id_a]
    node_b = graph.nodes[conn.shape_id_b]
    
    type_a = get_node_shape_type(node_a)
    type_b = get_node_shape_type(node_b)
    
    # Canonicalize edge indices using geometric symmetry
    # For basic shapes, use the shape's own polygon
    # For merged shapes, we need to find which constituent component the edge belongs to
    canon_edge_a = _canonicalize_edge_for_node(node_a, conn.edge_idx_a)
    canon_edge_b = _canonicalize_edge_for_node(node_b, conn.edge_idx_b)
    
    # Get rotation angles for relative angle calculation
    rot_a = float(node_a.get("rotation", 0.0))
    rot_b = float(node_b.get("rotation", 0.0))
    rel_angle = int(round((rot_b - rot_a) % 360))
    # Snap to 15 degrees
    rel_angle = (rel_angle // 15) * 15
    
    # Canonical ordering: ensure consistent key regardless of which shape is A vs B
    swap = False
    if type_a < type_b:
        swap = False
    elif type_a > type_b:
        swap = True
    else:
        # Same type: sort by canonical edge index
        if canon_edge_a > canon_edge_b:
            swap = True
        elif canon_edge_a == canon_edge_b:
            # Break ties by relative angle direction
            swap = rel_angle > 180
    
    if not swap:
        return MergePairKey(
            type_a=type_a,
            type_b=type_b,
            canon_edge_a=canon_edge_a,
            canon_edge_b=canon_edge_b,
            relative_angle=rel_angle,
        )
    else:
        return MergePairKey(
            type_a=type_b,
            type_b=type_a,
            canon_edge_a=canon_edge_b,
            canon_edge_b=canon_edge_a,
            relative_angle=((360 - rel_angle) % 360 // 15) * 15,
        )

def _canonicalize_edge_for_node(node: dict, edge_idx: int) -> int:
    """Canonicalize an edge index for a node, handling both basic and merged shapes.
    
    For basic shapes: directly canonicalize using the shape polygon's symmetry.
    For merged shapes: find which constituent component the edge belongs to,
    then canonicalize using that component's polygon symmetry. This keeps merge keys
    stable across BPE rounds.
    """
    if "components" not in node or not node["components"]:
        # Basic shape — canonicalize directly
        return canonicalize_edge_index(node["poly"], edge_idx)
    
    # Merged shape — find which component owns this edge
    poly = node["poly"]
    n = len(poly)
    if edge_idx >= n:
        return edge_idx
    
    # Get the midpoint of the edge on the merged shape
    p1 = poly[edge_idx]
    p2 = poly[(edge_idx + 1) % n]
    mid = {
        "x": (p1["x"] + p2["x"]) / 2.0,
        "y": (p1["y"] + p2["y"]) / 2.0
    }
    
    # Find which component this midpoint lies on
    for comp in node["components"]:
        comp_poly = comp["poly"]
        n_c = len(comp_poly)
        for ci in range(n_c):
            cp1 = comp_poly[ci]
            cp2 = comp_poly[(ci + 1) % n_c]
            d = distance(cp1, cp2)
            if d > 1e-5:
                d1 = distance(mid, cp1)
                d2 = distance(mid, cp2)
                if abs(d1 + d2 - d) < 1e-2:
                    # Found it — canonicalize using the component's polygon
                    return canonicalize_edge_index(comp_poly, ci)
    
    # Fallback: just return the raw edge index
    return edge_idx

# ─────────────────────────────────────────────────────────
# Polygon operations for merging
# ─────────────────────────────────────────────────────────

def simplify_polygon(poly: list[dict]) -> list[dict]:
    """Remove collinear or duplicate vertices from a polygon."""
    if len(poly) <= 3:
        return poly
    simplified = []
    n = len(poly)
    for i in range(n):
        p_prev = poly[(i - 1) % n]
        p_curr = poly[i]
        p_next = poly[(i + 1) % n]
        
        # Calculate cross product to check for collinearity
        dx1 = p_curr["x"] - p_prev["x"]
        dy1 = p_curr["y"] - p_prev["y"]
        dx2 = p_next["x"] - p_curr["x"]
        dy2 = p_next["y"] - p_curr["y"]
        
        cross = dx1 * dy2 - dy1 * dx2
        len1 = math.hypot(dx1, dy1)
        len2 = math.hypot(dx2, dy2)
        
        if len1 < 1e-5 or len2 < 1e-5:
            # Duplicate point, skip
            continue
            
        # If cross product is near zero, points are collinear
        if abs(cross) / (len1 * len2) < 1e-4:
            continue
            
        simplified.append(p_curr)
    return simplified

def find_full_overlap_segment(poly_a: list[dict], poly_b: list[dict], pt: dict) -> tuple[tuple[dict, dict], tuple[dict, dict]] | None:
    """Find the full overlapping boundary segment between two polygons containing a contact point."""
    edge_a = None
    n_a = len(poly_a)
    for i in range(n_a):
        p1 = poly_a[i]
        p2 = poly_a[(i + 1) % n_a]
        dx = p2["x"] - p1["x"]
        dy = p2["y"] - p1["y"]
        d = math.hypot(dx, dy)
        if d > 1e-5:
            d1 = math.hypot(pt["x"] - p1["x"], pt["y"] - p1["y"])
            d2 = math.hypot(pt["x"] - p2["x"], pt["y"] - p2["y"])
            if abs(d1 + d2 - d) < 1e-2:
                edge_a = (p1, p2)
                break
                
    edge_b = None
    n_b = len(poly_b)
    for i in range(n_b):
        q1 = poly_b[i]
        q2 = poly_b[(i + 1) % n_b]
        dx = q2["x"] - q1["x"]
        dy = q2["y"] - q1["y"]
        d = math.hypot(dx, dy)
        if d > 1e-5:
            d1 = math.hypot(pt["x"] - q1["x"], pt["y"] - q1["y"])
            d2 = math.hypot(pt["x"] - q2["x"], pt["y"] - q2["y"])
            if abs(d1 + d2 - d) < 1e-2:
                edge_b = (q1, q2)
                break
                
    if edge_a is None or edge_b is None:
        return None
        
    p1, p2 = edge_a
    q1, q2 = edge_b
    
    dx = p2["x"] - p1["x"]
    dy = p2["y"] - p1["y"]
    d2_val = dx*dx + dy*dy
    if d2_val < 1e-10:
        return None
        
    def project(p):
        return ((p["x"] - p1["x"]) * dx + (p["y"] - p1["y"]) * dy) / d2_val
        
    t_q1 = project(q1)
    t_q2 = project(q2)
    
    t_min = max(0.0, min(t_q1, t_q2))
    t_max = min(1.0, max(t_q1, t_q2))
    
    if t_max - t_min < 1e-3:
        return None
        
    overlap_a = (
        {"x": p1["x"] + t_min * dx, "y": p1["y"] + t_min * dy},
        {"x": p1["x"] + t_max * dx, "y": p1["y"] + t_max * dy}
    )
    overlap_b = (overlap_a[1], overlap_a[0])
    
    return overlap_a, overlap_b

def merge_polygons_at_edge(poly_a: list[dict], poly_b: list[dict], edge_a: tuple[dict, dict] = None, edge_b: tuple[dict, dict] = None) -> list[dict] | None:
    """Merge two polygons sharing one or more collinear, overlapping boundary segments.
    
    This splits the boundary of both polygons at all mutual overlap points, removes the
    coincident (shared) sub-segments, and chains the remaining exposed segments end-to-end
    to form a single clean unified outer polygon.
    """
    tolerance = 1e-2  # 1 cm coordinate snapping tolerance
    
    # 1. Collect all directed edges of A and B
    edges_a = []
    n_a = len(poly_a)
    for i in range(n_a):
        edges_a.append({"start": poly_a[i], "end": poly_a[(i + 1) % n_a]})
        
    edges_b = []
    n_b = len(poly_b)
    for i in range(n_b):
        edges_b.append({"start": poly_b[i], "end": poly_b[(i + 1) % n_b]})
        
    # 2. Project vertices of each polygon onto the edges of the other to find split points
    def get_splits(edges_to_split, other_poly):
        splits = defaultdict(list)
        for idx, edge in enumerate(edges_to_split):
            p1, p2 = edge["start"], edge["end"]
            dx = p2["x"] - p1["x"]
            dy = p2["y"] - p1["y"]
            d = math.hypot(dx, dy)
            if d < 1e-5:
                continue
            for pt in other_poly:
                d1 = distance(pt, p1)
                d2 = distance(pt, p2)
                if abs(d1 + d2 - d) < tolerance:
                    if d1 > 5e-3 and d2 > 5e-3:
                        splits[idx].append((d1 / d, pt))
        return splits

    splits_a = get_splits(edges_a, poly_b)
    splits_b = get_splits(edges_b, poly_a)
    
    # 3. Reconstruct split segments for both A and B
    segments_a = []
    for idx, edge in enumerate(edges_a):
        if idx in splits_a:
            sorted_splits = sorted(splits_a[idx], key=lambda x: x[0])
            curr = edge["start"]
            for _, pt in sorted_splits:
                segments_a.append({"start": curr, "end": pt})
                curr = pt
            segments_a.append({"start": curr, "end": edge["end"]})
        else:
            segments_a.append(edge)
            
    segments_b = []
    for idx, edge in enumerate(edges_b):
        if idx in splits_b:
            sorted_splits = sorted(splits_b[idx], key=lambda x: x[0])
            curr = edge["start"]
            for _, pt in sorted_splits:
                segments_b.append({"start": curr, "end": pt})
                curr = pt
            segments_b.append({"start": curr, "end": edge["end"]})
        else:
            segments_b.append(edge)
            
    # 4. Classify segments as exposed or shared (coincident with the other polygon's boundary)
    def is_shared(seg, other_segments):
        s_mid = {
            "x": (seg["start"]["x"] + seg["end"]["x"]) / 2.0,
            "y": (seg["start"]["y"] + seg["end"]["y"]) / 2.0
        }
        for o_seg in other_segments:
            o_mid = {
                "x": (o_seg["start"]["x"] + o_seg["end"]["x"]) / 2.0,
                "y": (o_seg["start"]["y"] + o_seg["end"]["y"]) / 2.0
            }
            if distance(s_mid, o_mid) < tolerance:
                return True
        return False
        
    exposed_a = [seg for seg in segments_a if not is_shared(seg, segments_b)]
    exposed_b = [seg for seg in segments_b if not is_shared(seg, segments_a)]
    
    # If no segments are shared, the polygons do not touch and cannot be merged.
    if len(exposed_a) == len(segments_a) and len(exposed_b) == len(segments_b):
        return None
        
    all_exposed = exposed_a + exposed_b
    if not all_exposed:
        return None
        
    # 5. Chain the exposed segments end-to-end to form the outer boundary loop
    merged_poly = []
    current_seg = all_exposed[0]
    merged_poly.append(current_seg["start"])
    all_exposed.remove(current_seg)
    
    start_pt = current_seg["start"]
    curr_pt = current_seg["end"]
    
    max_iters = len(all_exposed) + 10
    for _ in range(max_iters):
        if distance(curr_pt, start_pt) < tolerance:
            break
            
        next_seg = None
        for seg in all_exposed:
            if distance(seg["start"], curr_pt) < tolerance:
                next_seg = seg
                break
        if next_seg is None:
            # Fallback connection to start_pt if no next exposed segment aligns
            break
            
        merged_poly.append(next_seg["start"])
        curr_pt = next_seg["end"]
        all_exposed.remove(next_seg)
        
    if len(merged_poly) < 3:
        return None
        
    return simplify_polygon(merged_poly)

# ─────────────────────────────────────────────────────────
# BPE merge: creating and replacing merged modules
# ─────────────────────────────────────────────────────────

def _create_merged_module_from_edge(pair_key: MergePairKey, conn: EdgeConnection, graph: LayoutGraph, round_num: int) -> MergedModule | None:
    """Create a new MergedModule from an edge connection, returning None on geometry failure."""
    node_a = graph.nodes[conn.shape_id_a]
    node_b = graph.nodes[conn.shape_id_b]
    
    # Use the overlap midpoint to find the full shared boundary
    pt = {
        "x": (conn.overlap_start["x"] + conn.overlap_end["x"]) / 2.0,
        "y": (conn.overlap_start["y"] + conn.overlap_end["y"]) / 2.0
    }
    
    full_overlap = find_full_overlap_segment(node_a["poly"], node_b["poly"], pt)
    if full_overlap is not None:
        edge_a, edge_b = full_overlap
    else:
        # Fall back to the overlap segment from the EdgeConnection
        edge_a = (conn.overlap_start, conn.overlap_end)
        edge_b = (conn.overlap_end, conn.overlap_start)
    
    # Union their polygons
    union_poly = merge_polygons_at_edge(
        node_a["poly"],
        node_b["poly"],
        edge_a,
        edge_b
    )
    
    if union_poly is None:
        return None
    
    type_id = f"M_round{round_num}_{pair_key.type_a}_{pair_key.type_b}"
    name = f"Merged Module ({pair_key.type_a} + {pair_key.type_b})"
    
    # Collect components
    components = []
    for node in (node_a, node_b):
        if "components" in node and node["components"]:
            components.extend(node["components"])
        else:
            components.append(node)
            
    return MergedModule(type_id=type_id, name=name, poly=union_poly, components=components)

def _replace_pair_in_graph(graph: LayoutGraph, conn: EdgeConnection, merged: MergedModule) -> bool:
    """Replace two shapes in the graph with their merged module.
    
    Returns True if successful, False if the geometry union failed (non-destructive).
    """
    id_a = conn.shape_id_a
    id_b = conn.shape_id_b
    
    if id_a not in graph.nodes or id_b not in graph.nodes:
        return False
    
    node_a = graph.nodes[id_a]
    node_b = graph.nodes[id_b]
    
    # Compute the union for THIS specific graph's actual local coordinates
    pt = {
        "x": (conn.overlap_start["x"] + conn.overlap_end["x"]) / 2.0,
        "y": (conn.overlap_start["y"] + conn.overlap_end["y"]) / 2.0
    }
    
    full_overlap = find_full_overlap_segment(node_a["poly"], node_b["poly"], pt)
    if full_overlap is not None:
        edge_a, edge_b = full_overlap
    else:
        edge_a = (conn.overlap_start, conn.overlap_end)
        edge_b = (conn.overlap_end, conn.overlap_start)
    
    local_union_poly = merge_polygons_at_edge(
        node_a["poly"],
        node_b["poly"],
        edge_a,
        edge_b
    )
    
    if local_union_poly is None:
        # Geometry union failed — keep original shapes intact
        return False
    
    # Collect local components for this specific graph instance
    local_components = []
    for node in (node_a, node_b):
        if "components" in node and node["components"]:
            local_components.extend(node["components"])
        else:
            local_components.append(node)
    
    # Create the new merged node
    new_id = f"{id_a}_merge_{id_b}"
    graph.nodes[new_id] = {
        "id": new_id,
        "poly": local_union_poly,
        "shapeType": merged.type_id,
        "moduleId": f"{node_a.get('moduleId', node_a['id'])}+{node_b.get('moduleId', node_b['id'])}",
        "components": local_components,
        "category": node_a.get("category", "room"),
        "rotation": node_a.get("rotation", 0.0),
    }
    
    # Remove old nodes
    del graph.nodes[id_a]
    del graph.nodes[id_b]
    
    return True

# ─────────────────────────────────────────────────────────
# Post-merge analysis
# ─────────────────────────────────────────────────────────

def is_triangle_polygon(poly: list[dict]) -> bool:
    """Check if a polygon is a triangle based on its actual geometry (3 non-degenerate vertices)."""
    if not poly:
        return False
    simplified = simplify_polygon(poly)
    return len(simplified) == 3

def count_remaining_basic_types(graphs: list[LayoutGraph]) -> int:
    """Count how many unique basic (unmerged) shape types remain in the graphs."""
    types = set()
    for g in graphs:
        for node in g.nodes.values():
            shape_type = get_node_shape_type(node)
            if not shape_type.startswith("M_round"):
                types.add(shape_type)
    return len(types)

def count_post_merge_triangles(graphs: list[LayoutGraph]) -> list[dict]:
    """Count standalone triangles remaining after BPE merging.
    
    Only counts top-level nodes whose polygon is a triangle (3 vertices).
    Triangles that are components inside a merged non-triangle shape are NOT counted.
    Merged shapes whose final polygon is itself a triangle ARE counted.
    
    Returns a list of dicts with {area, is_merged} for each triangle found.
    """
    triangles = []
    for graph in graphs:
        for node in graph.nodes.values():
            poly = node["poly"]
            if is_triangle_polygon(poly):
                area = G.polygon_area(poly)
                is_merged = bool(node.get("shapeType", "").startswith("M_round"))
                triangles.append({"area": area, "is_merged": is_merged})
    return triangles

# ─────────────────────────────────────────────────────────
# Main BPE merge algorithm
# ─────────────────────────────────────────────────────────

def bpe_merge(
    layout_graphs: list[LayoutGraph],
    min_frequency: int = 2,
    max_rounds: int = 20,
    max_vocab_size: int = 30,
) -> tuple[list[MergedModule], dict]:
    """Iterative pairwise BPE merge across all parallel layout graphs.
    
    The algorithm:
    1. Find all full-edge adjacencies across all floors
    2. Count canonical pair frequencies globally
    3. Pick the most frequent pair that meets the threshold
    4. Attempt polygon union for all instances, non-destructively
    5. Repeat until no more merges or max rounds reached
    6. Post-processing: unmerge any merged shape with global frequency < 2
    
    Returns (vocabulary_list, stats_dict).
    """
    vocabulary = {}
    
    for round_num in range(max_rounds):
        # 1. Find edge connections across all graphs
        all_connections: list[tuple[int, EdgeConnection]] = []
        for graph_idx, graph in enumerate(layout_graphs):
            edge_conns = find_edge_connections(graph)
            for conn in edge_conns:
                all_connections.append((graph_idx, conn))
        
        if not all_connections:
            break
        
        # 2. Count canonical pair frequencies globally
        pair_counts: Counter = Counter()
        pair_instances: dict[MergePairKey, list[tuple[int, EdgeConnection]]] = defaultdict(list)
        
        for graph_idx, conn in all_connections:
            graph = layout_graphs[graph_idx]
            pair_key = canonicalize_merge_key(conn, graph)
            pair_counts[pair_key] += 1
            pair_instances[pair_key].append((graph_idx, conn))
            
        print(f"--- BPE ROUND {round_num} ---")
        print(f"Total connections found: {len(all_connections)}")
        print(f"Unique pair keys: {len(pair_counts)}")
        for pk, cnt in pair_counts.items():
            print(f"  Key: {pk.type_a} + {pk.type_b} (rel_angle={pk.relative_angle}, edges={pk.canon_edge_a}/{pk.canon_edge_b}) -> Count: {cnt}")
        
        # 3. Find the most frequent pair that can be merged geometrically
        best_pair = None
        best_merged = None
        
        for pair_key, count in pair_counts.most_common():
            if count < min_frequency:
                print(f"Skipping pair with count {count} < min_frequency {min_frequency}")
                break
            
            # Try to create the merged module from the first instance
            graph_idx, conn = pair_instances[pair_key][0]
            merged_candidate = _create_merged_module_from_edge(
                pair_key, conn, layout_graphs[graph_idx], round_num
            )
            if merged_candidate is not None:
                best_pair = pair_key
                best_merged = merged_candidate
                print(f"Selected best pair to merge: {pair_key.type_a} + {pair_key.type_b} (count={count}) -> Merged Type: {merged_candidate.type_id}")
                break
            else:
                print(f"Failed to geometrically merge pair: {pair_key.type_a} + {pair_key.type_b} (count={count})")
        
        if best_pair is None or best_merged is None:
            print("No mergeable pair found in this round.")
            break
        
        vocabulary[best_merged.type_id] = best_merged
        
        # 4. Replace all instances of this pair across all graphs
        merged_nodes_per_graph: dict[int, set] = defaultdict(set)
        
        for graph_idx, conn in pair_instances[best_pair]:
            id_a = conn.shape_id_a
            id_b = conn.shape_id_b
            
            # Skip if either node was already consumed in this round
            if id_a in merged_nodes_per_graph[graph_idx] or id_b in merged_nodes_per_graph[graph_idx]:
                continue
            
            success = _replace_pair_in_graph(layout_graphs[graph_idx], conn, best_merged)
            if success:
                merged_nodes_per_graph[graph_idx].add(id_a)
                merged_nodes_per_graph[graph_idx].add(id_b)
        
        if len(vocabulary) >= max_vocab_size:
            break
    
    # ─── Post-processing: unmerge singletons ───
    global_shape_counts = Counter()
    for graph in layout_graphs:
        for node in graph.nodes.values():
            st = node.get("shapeType", "")
            if st:
                global_shape_counts[st] += 1
    
    for graph in layout_graphs:
        nodes_to_unmerge = []
        for node_id, node in graph.nodes.items():
            shape_type = node.get("shapeType", "")
            if shape_type.startswith("M_round") and global_shape_counts[shape_type] < 2:
                nodes_to_unmerge.append(node_id)
        
        for node_id in nodes_to_unmerge:
            node = graph.nodes.pop(node_id)
            if "components" in node and node["components"]:
                for comp in node["components"]:
                    comp_id = comp["id"]
                    graph.nodes[comp_id] = comp
    
    # ─── Compute stats ───
    total_placements = sum(len(g.nodes) for g in layout_graphs)
    unique_types = len(vocabulary) + count_remaining_basic_types(layout_graphs)
    
    return list(vocabulary.values()), {
        "total_placements": total_placements,
        "unique_types": unique_types,
        "merge_rounds": len(vocabulary),
    }

# ─────────────────────────────────────────────────────────
# Legacy functions (kept for backward compatibility)
# ─────────────────────────────────────────────────────────

def canonicalize_geometry_port(shape_type: str, edge_index: int, half: str, poly: list[dict]) -> tuple[int, str]:
    """[DEPRECATED] Use canonicalize_edge_index instead. Kept for wall rendering compatibility."""
    if not poly or len(poly) < 3:
        return edge_index, half
        
    n = len(poly)
    lengths = _all_edge_lengths(poly)
        
    # 1. Equilateral Triangles (pure 2D rotational symmetry)
    if n == 3:
        if abs(lengths[0] - lengths[1]) < 1e-2 and abs(lengths[1] - lengths[2]) < 1e-2:
            return 0, half
            
    # 2. Parallelograms, Rectangles (180-degree 2D rotational symmetry)
    elif n == 4:
        if abs(lengths[0] - lengths[2]) < 1e-2 and abs(lengths[1] - lengths[3]) < 1e-2:
            if edge_index == 2:
                flipped_half = "R" if half == "L" else "L"
                return 0, flipped_half
            elif edge_index == 3:
                flipped_half = "R" if half == "L" else "L"
                return 1, flipped_half
                
    return edge_index, half

def canonicalize_port(port: Port, node: dict) -> tuple[str, int, str]:
    """[DEPRECATED] Kept for backward compatibility with wall rendering system."""
    res_type, res_edge, res_half = None, None, None
    res_poly = None
    if "components" not in node or not node["components"]:
        res_type = get_node_shape_type(node)
        res_edge, res_half = port.edge_index, port.half
        res_poly = node["poly"]
    else:
        pt_start = port.start
        pt_end = port.end
        pt_mid = {
            "x": (pt_start["x"] + pt_end["x"]) / 2.0,
            "y": (pt_start["y"] + pt_end["y"]) / 2.0
        }
        
        found = False
        for comp in node["components"]:
            poly = comp["poly"]
            n = len(poly)
            for i in range(n):
                p1 = poly[i]
                p2 = poly[(i + 1) % n]
                dx = p2["x"] - p1["x"]
                dy = p2["y"] - p1["y"]
                d = math.hypot(dx, dy)
                if d > 1e-5:
                    d1 = math.hypot(pt_mid["x"] - p1["x"], pt_mid["y"] - p1["y"])
                    d2 = math.hypot(pt_mid["x"] - p2["x"], pt_mid["y"] - p2["y"])
                    if abs(d1 + d2 - d) < 1e-2:
                        res_type = get_node_shape_type(comp)
                        def project(p):
                            return ((p["x"] - p1["x"]) * dx + (p["y"] - p1["y"]) * dy) / (d*d)
                        t1 = project(pt_start)
                        t2 = project(pt_end)
                        t_mid = (t1 + t2) / 2.0
                        half = "L" if t_mid < 0.5 else "R"
                        res_type, res_edge, res_half = res_type, i, half
                        res_poly = poly
                        found = True
                        break
            if found:
                break
                
        if not found:
            res_type = get_node_shape_type(node)
            res_edge, res_half = port.edge_index, port.half
            res_poly = node["poly"]
            
    canon_edge, canon_half = canonicalize_geometry_port(res_type, res_edge, res_half, res_poly)
    return (res_type, canon_edge, canon_half)

def canonicalize_pair(conn: PortConnection, graph: LayoutGraph) -> MergePairKey:
    """[DEPRECATED] Kept for backward compatibility. Use canonicalize_merge_key instead."""
    node_a = graph.nodes[conn.port_a.shape_id]
    node_b = graph.nodes[conn.port_b.shape_id]
    
    type_a = get_node_shape_type(node_a)
    type_b = get_node_shape_type(node_b)
    
    rot_a = float(node_a.get("rotation", 0.0))
    rot_b = float(node_b.get("rotation", 0.0))
    rel_angle = int(round((rot_b - rot_a) % 360))
    rel_angle = (rel_angle // 15) * 15
    
    port_id_a = canonicalize_port(conn.port_a, node_a)
    port_id_b = canonicalize_port(conn.port_b, node_b)
    
    swap = False
    if type_a < type_b:
        swap = False
    elif type_a > type_b:
        swap = True
    else:
        swap = (port_id_a > port_id_b)
        
    if not swap:
        return MergePairKey(
            type_a=type_a,
            type_b=type_b,
            canon_edge_a=port_id_a[1],
            canon_edge_b=port_id_b[1],
            relative_angle=rel_angle
        )
    else:
        return MergePairKey(
            type_a=type_b,
            type_b=type_a,
            canon_edge_a=port_id_b[1],
            canon_edge_b=port_id_a[1],
            relative_angle=int(round((-rel_angle) % 360 // 15 * 15))
        )
