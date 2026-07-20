import math
from dataclasses import dataclass
from collections import Counter, defaultdict
from typing import Sequence, Any
import geometry as G

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
    connections: list[PortConnection] # list of port-to-port connections
    playground_id: int

@dataclass(frozen=True)
class MergePairKey:
    type_a: str          # e.g., "Q_rect_M"
    type_b: str          # e.g., "Q_rect_S"
    # Canonical port identifiers: e.g., (original_edge_index, "L" or "R")
    ports_a: frozenset   # set of ports of A involved in connection
    ports_b: frozenset   # set of ports of B involved in connection
    relative_angle: int  # relative angle between A and B, in degrees (snapped to 15°)

@dataclass
class MergedModule:
    type_id: str
    name: str
    poly: list[dict]
    components: list[dict] # list of basic shapes that make it up

def distance(p1: dict, p2: dict) -> float:
    return math.hypot(p2["x"] - p1["x"], p2["y"] - p1["y"])

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

def canonicalize_geometry_port(shape_type: str, edge_index: int, half: str, poly: list[dict]) -> tuple[int, str]:
    """Normalize symmetric port edge indices and directions for standard shapes using robust geometry checks."""
    if not poly or len(poly) < 3:
        return edge_index, half
        
    n = len(poly)
    lengths = []
    for i in range(n):
        p1 = poly[i]
        p2 = poly[(i + 1) % n]
        lengths.append(math.hypot(p2["x"] - p1["x"], p2["y"] - p1["y"]))
        
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
    """Find the constituent basic shape port that this port segment belongs to for stable key matching."""
    res_type, res_edge, res_half = None, None, None
    res_poly = None
    if "components" not in node or not node["components"]:
        # Basic shape
        res_type = get_node_shape_type(node)
        res_edge, res_half = port.edge_index, port.half
        res_poly = node["poly"]
    else:
        # Merged shape: find which component's boundary contains the port segment
        pt_start = port.start
        pt_end = port.end
        
        # Midpoint of the port segment
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
                        # Found the component and the edge!
                        res_type = get_node_shape_type(comp)
                        
                        # Project midpoint to determine half relative to p1
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
            # Fallback: use the node's own port edge index
            res_type = get_node_shape_type(node)
            res_edge, res_half = port.edge_index, port.half
            res_poly = node["poly"]
            
    # Run through the geometry symmetry normalizer
    canon_edge, canon_half = canonicalize_geometry_port(res_type, res_edge, res_half, res_poly)
    return (res_type, canon_edge, canon_half)

def canonicalize_pair(conn: PortConnection, graph: LayoutGraph) -> MergePairKey:
    """Create a canonical rotation-invariant key for a port-to-port connection."""
    node_a = graph.nodes[conn.port_a.shape_id]
    node_b = graph.nodes[conn.port_b.shape_id]
    
    type_a = get_node_shape_type(node_a)
    type_b = get_node_shape_type(node_b)
    
    # Get rotation angles
    rot_a = float(node_a.get("rotation", 0.0))
    rot_b = float(node_b.get("rotation", 0.0))
    rel_angle = int(round((rot_b - rot_a) % 360))
    # Snap to 15 degrees
    rel_angle = (rel_angle // 15) * 15
    
    port_id_a = canonicalize_port(conn.port_a, node_a)
    port_id_b = canonicalize_port(conn.port_b, node_b)
    
    # Canonical ordering based on port_id_a and port_id_b
    swap = False
    if type_a < type_b:
        swap = False
    elif type_a > type_b:
        swap = True
    else:  # type_a == type_b
        swap = (port_id_a > port_id_b)
        
    if not swap:
        return MergePairKey(
            type_a=type_a,
            type_b=type_b,
            ports_a=frozenset([port_id_a]),
            ports_b=frozenset([port_id_b]),
            relative_angle=rel_angle
        )
    else:
        # Swap A and B. Relative angle is inverted.
        return MergePairKey(
            type_a=type_b,
            type_b=type_a,
            ports_a=frozenset([port_id_b]),
            ports_b=frozenset([port_id_a]),
            relative_angle=int(round((-rel_angle) % 360 // 15 * 15))
        )

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

def merge_polygons_at_edge(poly_a: list[dict], poly_b: list[dict], edge_a: tuple[dict, dict], edge_b: tuple[dict, dict]) -> list[dict]:
    """Merge two polygons sharing a collinear, overlapping edge segment."""
    # 1. Insert midpoint/endpoints of overlap into both polygons to split edges flush
    # For robust segment merging, we insert the overlapping vertices into both loops
    def insert_vertex_on_segment(poly: list[dict], start: dict, end: dict, pt: dict) -> list[dict]:
        new_poly = []
        n = len(poly)
        inserted = False
        for i in range(n):
            p1 = poly[i]
            p2 = poly[(i + 1) % n]
            new_poly.append(p1)
            # Check if pt lies on segment p1-p2
            if not inserted:
                dx = p2["x"] - p1["x"]
                dy = p2["y"] - p1["y"]
                d = math.hypot(dx, dy)
                if d > 1e-5:
                    d1 = math.hypot(pt["x"] - p1["x"], pt["y"] - p1["y"])
                    d2 = math.hypot(pt["x"] - p2["x"], pt["y"] - p2["y"])
                    # Use a looser 1cm tolerance to handle floating point precision on rotated coordinates
                    if abs(d1 + d2 - d) < 1e-2:
                        # Check if duplicate (at least 5mm away from existing vertices)
                        if d1 > 5e-3 and d2 > 5e-3:
                            new_poly.append(pt)
                            inserted = True
        return new_poly

    p_a = list(poly_a)
    p_b = list(poly_b)
    
    # Insert intersection endpoints
    p_a = insert_vertex_on_segment(p_a, edge_a[0], edge_a[1], edge_b[0])
    p_a = insert_vertex_on_segment(p_a, edge_a[0], edge_a[1], edge_b[1])
    p_b = insert_vertex_on_segment(p_b, edge_b[0], edge_b[1], edge_a[0])
    p_b = insert_vertex_on_segment(p_b, edge_b[0], edge_b[1], edge_a[1])
    
    # 2. Find matching indices
    # We want to find index i in p_a and index j in p_b such that:
    # p_a[i] == p_b[j+1] and p_a[i+1] == p_b[j] (anti-parallel matching segment)
    n_a = len(p_a)
    n_b = len(p_b)
    match_a = -1
    match_b = -1
    for i in range(n_a):
        p1 = p_a[i]
        p2 = p_a[(i + 1) % n_a]
        for j in range(n_b):
            q1 = p_b[j]
            q2 = p_b[(j + 1) % n_b]
            # Use 1cm tolerance for vertex matching
            if distance(p1, q2) < 1e-2 and distance(p2, q1) < 1e-2:
                match_a = i
                match_b = j
                break
        if match_a != -1:
            break
            
    if match_a == -1:
        # Fallback: if no exact matching segment found, return None to signal failure
        return None
        
    # 3. Walk loop to construct union
    merged_poly = []
    # Walk A from match_a+1 (end of shared segment) all the way to match_a (start of shared segment)
    for idx in range(n_a):
        curr_idx = (match_a + 1 + idx) % n_a
        merged_poly.append(p_a[curr_idx])
        
    # Walk B from match_b+2 (after shared segment start) all the way to match_b (start of shared segment on B)
    # Note that B's shared segment is from match_b to match_b+1, which matches A's match_a+1 to match_a.
    for idx in range(n_b - 2):
        curr_idx = (match_b + 2 + idx) % n_b
        merged_poly.append(p_b[curr_idx])
        
    return simplify_polygon(merged_poly)

def create_merged_module(pair_key: MergePairKey, conn: PortConnection, graph: LayoutGraph, round_num: int) -> MergedModule:
    """Create a new MergedModule representing the union of the two shapes in the connection."""
    node_a = graph.nodes[conn.port_a.shape_id]
    node_b = graph.nodes[conn.port_b.shape_id]
    
    pt = conn.port_a.start
    if conn.overlap_segment is not None:
        pt = {
            "x": (conn.overlap_segment[0]["x"] + conn.overlap_segment[1]["x"]) / 2.0,
            "y": (conn.overlap_segment[0]["y"] + conn.overlap_segment[1]["y"]) / 2.0
        }
    else:
        pt = {
            "x": (conn.port_a.start["x"] + conn.port_a.end["x"]) / 2.0,
            "y": (conn.port_a.start["y"] + conn.port_a.end["y"]) / 2.0
        }
        
    full_overlap = find_full_overlap_segment(node_a["poly"], node_b["poly"], pt)
    if full_overlap is not None:
        edge_a, edge_b = full_overlap
    else:
        edge_a = (conn.port_a.start, conn.port_a.end)
        edge_b = (conn.port_b.end, conn.port_b.start)
        if conn.overlap_segment is not None:
            edge_a = conn.overlap_segment
            edge_b = (conn.overlap_segment[1], conn.overlap_segment[0])
        
    # Union their polygons
    union_poly = merge_polygons_at_edge(
        node_a["poly"],
        node_b["poly"],
        edge_a,
        edge_b
    )
    
    type_id = f"M_round{round_num}_{pair_key.type_a}_{pair_key.type_b}"
    name = f"Merged Module ({pair_key.type_a} + {pair_key.type_b})"
    
    # Collect components
    components = []
    for node in (node_a, node_b):
        if "components" in node:
            components.extend(node["components"])
        else:
            components.append(node)
            
    return MergedModule(type_id=type_id, name=name, poly=union_poly, components=components)

def replace_pair_with_merged(graph: LayoutGraph, conn: PortConnection, merged: MergedModule) -> None:
    """Update the layout graph by removing the two merged shapes and inserting the new MergedModule."""
    id_a = conn.port_a.shape_id
    id_b = conn.port_b.shape_id
    
    if id_a not in graph.nodes or id_b not in graph.nodes:
        return
        
    node_a = graph.nodes[id_a]
    node_b = graph.nodes[id_b]
    
    pt = conn.port_a.start
    if conn.overlap_segment is not None:
        pt = {
            "x": (conn.overlap_segment[0]["x"] + conn.overlap_segment[1]["x"]) / 2.0,
            "y": (conn.overlap_segment[0]["y"] + conn.overlap_segment[1]["y"]) / 2.0
        }
    else:
        pt = {
            "x": (conn.port_a.start["x"] + conn.port_a.end["x"]) / 2.0,
            "y": (conn.port_a.start["y"] + conn.port_a.end["y"]) / 2.0
        }
        
    full_overlap = find_full_overlap_segment(node_a["poly"], node_b["poly"], pt)
    if full_overlap is not None:
        edge_a, edge_b = full_overlap
    else:
        edge_a = (conn.port_a.start, conn.port_a.end)
        edge_b = (conn.port_b.end, conn.port_b.start)
        if conn.overlap_segment is not None:
            edge_a = conn.overlap_segment
            edge_b = (conn.overlap_segment[1], conn.overlap_segment[0])
        
    # Union their actual local polygons to preserve local/world coordinates for this playground!
    local_union_poly = merge_polygons_at_edge(
        node_a["poly"],
        node_b["poly"],
        edge_a,
        edge_b
    )
    
    if local_union_poly is None:
        # If geometry union fails, abort BPE merge for this instance and keep original shapes
        return
        
    # Collect components for this specific playground/instance to keep correct local coordinates
    local_components = []
    for node in (node_a, node_b):
        if "components" in node:
            local_components.extend(node["components"])
        else:
            local_components.append(node)

    # Create the new node in the graph
    new_id = f"{id_a}_merge_{id_b}"
    graph.nodes[new_id] = {
        "id": new_id,
        "poly": local_union_poly,
        "shapeType": merged.type_id,
        "moduleId": f"{node_a.get('moduleId', node_a['id'])}+{node_b.get('moduleId', node_b['id'])}",
        "components": local_components,
        "category": "room", # default category after merge
    }
    
    # Remove old nodes
    del graph.nodes[id_a]
    del graph.nodes[id_b]
    
    # Re-extract connections for the updated nodes in the graph
    # To keep it simple and robust, we just re-run extract_layout_graph on the remaining nodes
    updated_placements = list(graph.nodes.values())
    temp_graph = extract_layout_graph(updated_placements, graph.playground_id)
    graph.connections = temp_graph.connections

def count_remaining_basic_types(graphs: list[LayoutGraph]) -> int:
    """Count how many unique basic (unmerged) shape types remain in the graphs."""
    types = set()
    for g in graphs:
        for node in g.nodes.values():
            shape_type = node.get("shapeType")
            if not shape_type:
                module_id = node.get("moduleId", "")
                parts = module_id.split("-")
                shape_type = parts[3] if len(parts) > 3 else (parts[-1] if parts else node["id"])
            if not shape_type.startswith("M_round"):
                types.add(shape_type)
    return len(types)

def bpe_merge(
    layout_graphs: list[LayoutGraph],
    min_frequency: int = 2,
    max_rounds: int = 20,
    max_vocab_size: int = 30,
) -> tuple[list[MergedModule], dict]:
    """Iterative pairwise BPE merge across all parallel layout graphs."""
    vocabulary = {}
    
    for round_num in range(max_rounds):
        # 1. Count connection pair frequencies across all playgrounds
        pair_counts = Counter()
        pair_instances = defaultdict(list)
        
        for graph_idx, graph in enumerate(layout_graphs):
            for connection in graph.connections:
                pair_key = canonicalize_pair(connection, graph)
                pair_counts[pair_key] += 1
                pair_instances[pair_key].append((graph_idx, connection))
                
        if not pair_counts:
            break
            
        # 2. Find the most frequent pair that can be merged geometrically
        best_pair = None
        merged = None
        for pair, count in pair_counts.most_common():
            if count < min_frequency:
                break
            graph_idx, conn = pair_instances[pair][0]
            merged_candidate = create_merged_module(pair, conn, layout_graphs[graph_idx], round_num)
            if merged_candidate.poly is not None:
                best_pair = pair
                merged = merged_candidate
                break
                
        if best_pair is None or merged is None:
            break
            
        vocabulary[merged.type_id] = merged
        
        # 4. Replace all occurrences in all graphs
        # Track which nodes we have already merged in this round to avoid double merging the same node twice
        merged_nodes_per_graph = defaultdict(set)
        
        for graph_idx, conn in pair_instances[best_pair]:
            id_a = conn.port_a.shape_id
            id_b = conn.port_b.shape_id
            
            # Skip if either node was already merged in a previous step in this round
            if id_a in merged_nodes_per_graph[graph_idx] or id_b in merged_nodes_per_graph[graph_idx]:
                continue
                
            replace_pair_with_merged(layout_graphs[graph_idx], conn, merged)
            merged_nodes_per_graph[graph_idx].add(id_a)
            merged_nodes_per_graph[graph_idx].add(id_b)
            
        if len(vocabulary) >= max_vocab_size:
            break
            
    # Post-processing: Unmerge any merged shape type that has a global frequency < 2
    global_shape_counts = Counter()
    for graph in layout_graphs:
        for node in graph.nodes.values():
            global_shape_counts[node.get("shapeType", "")] += 1
            
    for graph in layout_graphs:
        nodes_to_unmerge = []
        for node_id, node in graph.nodes.items():
            shape_type = node.get("shapeType", "")
            if shape_type.startswith("M_round") and global_shape_counts[shape_type] < 2:
                nodes_to_unmerge.append(node_id)
                
        for node_id in nodes_to_unmerge:
            node = graph.nodes.pop(node_id)
            if "components" in node:
                for comp in node["components"]:
                    comp_id = comp["id"]
                    graph.nodes[comp_id] = comp
                    
    total_placements = sum(len(g.nodes) for g in layout_graphs)
    unique_types = len(vocabulary) + count_remaining_basic_types(layout_graphs)
    
    return list(vocabulary.values()), {
        "total_placements": total_placements,
        "unique_types": unique_types,
        "merge_rounds": len(vocabulary),
    }
