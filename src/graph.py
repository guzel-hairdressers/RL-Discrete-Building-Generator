from __future__ import annotations

import math
import hashlib
import json
from dataclasses import dataclass, field
from collections import Counter, defaultdict
from typing import Sequence, Any
import geometry as G


# BPE geometry is intentionally a little more tolerant than the placement
# kernel.  Placement coordinates may contain rounded trigonometric values, but
# modules are still measured in metres, so 1 cm is a conservative upper bound
# for treating two intended wall lines as coincident.
BPE_SNAP_TOLERANCE = 1.0e-2
BPE_ANGULAR_TOLERANCE = 1.0e-3
BPE_ENDPOINT_TOLERANCE = 1.0e-4
BPE_MIN_OVERLAP_FRACTION = 0.90
BPE_SIGNATURE_GRID = 1.0e-3
BPE_AREA_REL_TOLERANCE = 1.0e-6
BPE_AREA_ABS_TOLERANCE = 1.0e-6

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
    """Canonical rotation-only key for a pair of adjacent shapes.

    ``geometry_signature`` is the identity-bearing field.  It describes both
    polygons in one common frame, is invariant to translation, common rigid
    rotation, input order, and cyclic vertex starts, and deliberately remains
    sensitive to reflection and along-edge attachment.  The edge and angle
    fields are retained as useful diagnostics and for API compatibility; they
    are not safe identifiers on their own because symmetric traversal can turn
    60 degrees into 300 degrees.
    """
    type_a: str          # e.g., "s3", "Q_rect_M"
    type_b: str          # e.g., "s3", "Q_rect_S"
    canon_edge_a: int = field(compare=False)  # symmetry-normalized diagnostic
    canon_edge_b: int = field(compare=False)  # symmetry-normalized diagnostic
    relative_angle: int = field(compare=False)  # snapped diagnostic only
    geometry_signature: str = ""

@dataclass
class MergedModule:
    type_id: str
    name: str
    poly: list[dict]
    components: list[dict] # list of basic shapes that make it up
    geometry_signature: str = ""

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

def _segments_collinear(
    first: dict,
    second: dict,
    third: dict,
    fourth: dict,
    tolerance: float = BPE_SNAP_TOLERANCE,
) -> bool:
    """Return whether two finite segments lie on the same tolerant line.

    Linear and angular error are deliberately checked separately.  The v0.5.1
    implementation used the 1 cm linear tolerance as an angular sine as well,
    accepting visibly skewed walls.  Here a rounded slanted edge can be up to
    1 cm off the line while its direction must still agree to roughly 0.057°.
    The predicate is symmetric in its two segment arguments.
    """
    first_length = distance(first, second)
    second_length = distance(third, fourth)
    if first_length <= 1e-5 or second_length <= 1e-5:
        return False
        
    dx1 = second["x"] - first["x"]
    dy1 = second["y"] - first["y"]
    dx2 = fourth["x"] - third["x"]
    dy2 = fourth["y"] - third["y"]
    
    direction_cross = abs(dx1 * dy2 - dy1 * dx2) / (first_length * second_length)
    if direction_cross > BPE_ANGULAR_TOLERANCE:
        return False
        
    def orient(p, q, r):
        return (q["x"] - p["x"]) * (r["y"] - p["y"]) - (q["y"] - p["y"]) * (r["x"] - p["x"])
        
    return (
        abs(orient(first, second, third)) <= tolerance * first_length
        and abs(orient(first, second, fourth)) <= tolerance * first_length
        and abs(orient(third, fourth, first)) <= tolerance * second_length
        and abs(orient(third, fourth, second)) <= tolerance * second_length
    )

def _overlap_interval_on_first(
    first: dict,
    second: dict,
    third: dict,
    fourth: dict,
    tolerance: float = BPE_SNAP_TOLERANCE,
) -> tuple[float, float] | None:
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


def _symmetric_overlap_measure_python(
    first: dict,
    second: dict,
    third: dict,
    fourth: dict,
    tolerance: float = BPE_SNAP_TOLERANCE,
) -> tuple[tuple[float, float], tuple[float, float], float] | None:
    """Measure collinear overlap conservatively in both segment frames.

    Projection onto only the arbitrarily selected first segment made the 90%
    decision insertion-order dependent for slightly skewed walls.  Returning
    the smaller of the two projected physical lengths makes both ordering
    directions take the same inclusive/reject decision.
    """

    first_interval = _overlap_interval_on_first(
        first, second, third, fourth, tolerance
    )
    second_interval = _overlap_interval_on_first(
        third, fourth, first, second, tolerance
    )
    if first_interval is None or second_interval is None:
        return None
    first_length = distance(first, second)
    second_length = distance(third, fourth)
    first_overlap = (first_interval[1] - first_interval[0]) * first_length
    second_overlap = (second_interval[1] - second_interval[0]) * second_length
    return first_interval, second_interval, min(first_overlap, second_overlap)


def _symmetric_overlap_measure(
    first: dict,
    second: dict,
    third: dict,
    fourth: dict,
    tolerance: float = BPE_SNAP_TOLERANCE,
) -> tuple[tuple[float, float], tuple[float, float], float] | None:
    """Dispatch the BPE overlap primitive to the parity-checked native kernel."""

    return G.symmetric_segment_overlap(
        first,
        second,
        third,
        fourth,
        linear_tolerance=tolerance,
        angular_tolerance=BPE_ANGULAR_TOLERANCE,
    )

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
        bounds_a = G.bounds_of(nodes[pid_a]["poly"])
        for j in range(i + 1, n_placements):
            pid_b = pids[j]
            bounds_b = G.bounds_of(nodes[pid_b]["poly"])
            if (
                bounds_a["maxX"] < bounds_b["minX"] - 0.5
                or bounds_b["maxX"] < bounds_a["minX"] - 0.5
                or bounds_a["maxY"] < bounds_b["minY"] - 0.5
                or bounds_b["maxY"] < bounds_a["minY"] - 0.5
            ):
                continue
            ports_b = all_ports[pid_b]
            
            for pa in ports_a:
                min_pax = pa.start["x"] if pa.start["x"] < pa.end["x"] else pa.end["x"]
                max_pax = pa.end["x"] if pa.start["x"] < pa.end["x"] else pa.start["x"]
                min_pay = pa.start["y"] if pa.start["y"] < pa.end["y"] else pa.end["y"]
                max_pay = pa.end["y"] if pa.start["y"] < pa.end["y"] else pa.start["y"]
                for pb in ports_b:
                    min_pbx = pb.start["x"] if pb.start["x"] < pb.end["x"] else pb.end["x"]
                    max_pbx = pb.end["x"] if pb.start["x"] < pb.end["x"] else pb.start["x"]
                    if max_pax < min_pbx - 0.1 or max_pbx < min_pax - 0.1:
                        continue
                    min_pby = pb.start["y"] if pb.start["y"] < pb.end["y"] else pb.end["y"]
                    max_pby = pb.end["y"] if pb.start["y"] < pb.end["y"] else pb.start["y"]
                    if max_pay < min_pby - 0.1 or max_pby < min_pay - 0.1:
                        continue

                    # Check if port segments A and B are collinear and overlap
                    # Since ports are directed (start -> end), anti-parallel ports connect.
                    # We check if segment A (pa.start -> pa.end) overlaps with segment B (pb.end -> pb.start)
                    overlap_measure = _symmetric_overlap_measure(
                        pa.start, pa.end, pb.end, pb.start
                    )
                    if overlap_measure is not None:
                        (start, end), _, shared_length = overlap_measure
                        port_a_length = distance(pa.start, pa.end)
                        port_b_length = distance(pb.start, pb.end)
                        shorter_length = min(port_a_length, port_b_length)
                        # Adjacency is defined symmetrically against the shorter
                        # port, making the result independent of placement order.
                        if shared_length + 1.0e-12 >= BPE_MIN_OVERLAP_FRACTION * shorter_length:
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
    by at least 90% of the shorter edge's length. This is much more robust than
    the half-edge port system since it checks the entire edge, not just halves.
    """
    connections = []
    pids = list(graph.nodes.keys())
    n = len(pids)
    
    node_bounds = {pid: G.bounds_of(graph.nodes[pid]["poly"]) for pid in pids}
    
    for i in range(n):
        pid_a = pids[i]
        node_a = graph.nodes[pid_a]
        poly_a = node_a["poly"]
        n_a = len(poly_a)
        ba = node_bounds[pid_a]
        
        for j in range(i + 1, n):
            pid_b = pids[j]
            bb = node_bounds[pid_b]
            if (
                ba["maxX"] < bb["minX"] - 0.1
                or bb["maxX"] < ba["minX"] - 0.1
                or ba["maxY"] < bb["minY"] - 0.1
                or bb["maxY"] < ba["minY"] - 0.1
            ):
                continue

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
                min_ax = a1["x"] if a1["x"] < a2["x"] else a2["x"]
                max_ax = a2["x"] if a1["x"] < a2["x"] else a1["x"]
                min_ay = a1["y"] if a1["y"] < a2["y"] else a2["y"]
                max_ay = a2["y"] if a1["y"] < a2["y"] else a1["y"]
                    
                for eb in range(n_b):
                    b1 = poly_b[eb]
                    b2 = poly_b[(eb + 1) % n_b]
                    len_b = distance(b1, b2)
                    if len_b < 1e-5:
                        continue
                    min_bx = b1["x"] if b1["x"] < b2["x"] else b2["x"]
                    max_bx = b2["x"] if b1["x"] < b2["x"] else b1["x"]
                    if max_ax < min_bx - 0.1 or max_bx < min_ax - 0.1:
                        continue
                    min_by = b1["y"] if b1["y"] < b2["y"] else b2["y"]
                    max_by = b2["y"] if b1["y"] < b2["y"] else b1["y"]
                    if max_ay < min_by - 0.1 or max_by < min_ay - 0.1:
                        continue
                    
                    overlap_measure = _symmetric_overlap_measure(a1, a2, b1, b2)

                    if overlap_measure is not None:
                        (t_start, t_end), _, overlap_abs_len = overlap_measure
                        min_edge_len = min(len_a, len_b)
                        
                        # Canonical contract: at least 90% of the shorter edge.
                        if (
                            overlap_abs_len + 1.0e-12 >= BPE_MIN_OVERLAP_FRACTION * min_edge_len
                            and overlap_abs_len > best_overlap_len
                        ):
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
                            
                            best_conn = EdgeConnection(
                                shape_id_a=pid_a,
                                shape_id_b=pid_b,
                                edge_idx_a=ea,
                                edge_idx_b=eb,
                                overlap_start=ov_start,
                                overlap_end=ov_end,
                                overlap_fraction_a=overlap_abs_len / len_a,
                                overlap_fraction_b=overlap_abs_len / len_b,
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


def _counter_clockwise_polygon(poly: Sequence[dict]) -> list[dict]:
    """Return a finite polygon copy with canonical counter-clockwise winding."""

    try:
        result = [
            {"x": float(point["x"]), "y": float(point["y"])}
            for point in poly
        ]
    except (KeyError, TypeError, ValueError):
        return []
    if any(
        not math.isfinite(point["x"]) or not math.isfinite(point["y"])
        for point in result
    ):
        return []
    if len(result) >= 3 and G.polygon_signed_area(result) < 0.0:
        result.reverse()
    return result


def _minimum_cyclic_tuple(values: Sequence[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    """Canonicalize only the cyclic start; never reverse boundary direction."""

    if not values:
        return ()
    sequence = tuple(values)
    return min(sequence[index:] + sequence[:index] for index in range(len(sequence)))


def pair_geometry_signature(node_a: dict, node_b: dict) -> str:
    """Return a stable translation/rotation-only signature for a placed pair.

    The signature enumerates every directed boundary edge as a possible +X
    reference axis, then chooses the lexicographically smallest common-frame
    representation.  Both polygons are encoded together and tagged by shape
    type.  Common translation and rigid rotation therefore disappear, while a
    reflection reverses the canonical CCW boundary sequence and remains a
    distinct configuration.  Quantization absorbs sub-millimetre trig noise.
    """

    tagged_polygons = [
        (get_node_shape_type(node_a), _counter_clockwise_polygon(node_a.get("poly", []))),
        (get_node_shape_type(node_b), _counter_clockwise_polygon(node_b.get("poly", []))),
    ]
    if any(len(poly) < 3 for _, poly in tagged_polygons):
        return "invalid"

    candidates: list[tuple] = []
    reference_edges = []
    for _, poly in tagged_polygons:
        for index, start in enumerate(poly):
            end = poly[(index + 1) % len(poly)]
            length = distance(start, end)
            if length > 1.0e-9:
                reference_edges.append((start, end, length))

    for origin, axis_end, axis_length in reference_edges:
        unit_x = (axis_end["x"] - origin["x"]) / axis_length
        unit_y = (axis_end["y"] - origin["y"]) / axis_length
        encoded_polygons = []
        for shape_type, poly in tagged_polygons:
            encoded_points = []
            for point in poly:
                relative_x = point["x"] - origin["x"]
                relative_y = point["y"] - origin["y"]
                rotated_x = relative_x * unit_x + relative_y * unit_y
                rotated_y = -relative_x * unit_y + relative_y * unit_x
                encoded_points.append(
                    (
                        int(round(rotated_x / BPE_SIGNATURE_GRID)),
                        int(round(rotated_y / BPE_SIGNATURE_GRID)),
                    )
                )
            encoded_polygons.append((shape_type, _minimum_cyclic_tuple(encoded_points)))
        candidates.append(tuple(sorted(encoded_polygons)))

    if not candidates:
        return "invalid"
    return json.dumps(min(candidates), separators=(",", ":"))

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
    rel_angle = int(round(((rot_b - rot_a) % 360) / 15.0) * 15) % 360
    geometry_signature = pair_geometry_signature(node_a, node_b)
    
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
            geometry_signature=geometry_signature,
        )
    else:
        return MergePairKey(
            type_a=type_b,
            type_b=type_a,
            canon_edge_a=canon_edge_b,
            canon_edge_b=canon_edge_a,
            relative_angle=(-rel_angle) % 360,
            geometry_signature=geometry_signature,
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


def _bounded_snap_area_tolerance(poly_a: Sequence[dict], poly_b: Sequence[dict]) -> float:
    """Return the maximum *positive* area strip allowed for contact snapping.

    For two intended shared walls separated by numeric perpendicular error
    ``d``, projecting them to one common line can change the single-ring union
    by at most ``shared_length * d``.  Summing only qualifying opposite-facing
    contact intervals gives a geometry-derived bound instead of a broad area
    percentage.  This allowance is intentionally one-sided: an apparent
    overlap that would remove filled area still has only the tight numeric
    tolerance.  Exact contacts retain that tight tolerance in both directions.
    """

    ba = G.bounds_of(poly_a)
    bb = G.bounds_of(poly_b)
    if (
        ba["maxX"] < bb["minX"] - 0.1
        or bb["maxX"] < ba["minX"] - 0.1
        or ba["maxY"] < bb["minY"] - 0.1
        or bb["maxY"] < ba["minY"] - 0.1
    ):
        return allowance

    expected_area = G.polygon_area(poly_a) + G.polygon_area(poly_b)
    allowance = max(BPE_AREA_ABS_TOLERANCE, expected_area * BPE_AREA_REL_TOLERANCE)
    for first_index, first in enumerate(poly_a):
        second = poly_a[(first_index + 1) % len(poly_a)]
        first_length = distance(first, second)
        if first_length <= 1.0e-9:
            continue
        first_dx = second["x"] - first["x"]
        first_dy = second["y"] - first["y"]
        min_1x = first["x"] if first["x"] < second["x"] else second["x"]
        max_1x = second["x"] if first["x"] < second["x"] else first["x"]
        min_1y = first["y"] if first["y"] < second["y"] else second["y"]
        max_1y = second["y"] if first["y"] < second["y"] else first["y"]

        for third_index, third in enumerate(poly_b):
            fourth = poly_b[(third_index + 1) % len(poly_b)]
            second_length = distance(third, fourth)
            if second_length <= 1.0e-9:
                continue
            min_2x = third["x"] if third["x"] < fourth["x"] else fourth["x"]
            max_2x = fourth["x"] if third["x"] < fourth["x"] else third["x"]
            if max_1x < min_2x - 0.1 or max_2x < min_1x - 0.1:
                continue
            min_2y = third["y"] if third["y"] < fourth["y"] else fourth["y"]
            max_2y = fourth["y"] if third["y"] < fourth["y"] else third["y"]
            if max_1y < min_2y - 0.1 or max_2y < min_1y - 0.1:
                continue

            measure = _symmetric_overlap_measure(first, second, third, fourth)
            if measure is None:
                continue
            _, _, shared_length = measure
            if shared_length <= BPE_ENDPOINT_TOLERANCE:
                continue
            second_dx = fourth["x"] - third["x"]
            second_dy = fourth["y"] - third["y"]
            direction_dot = (
                first_dx * second_dx + first_dy * second_dy
            ) / (first_length * second_length)
            if direction_dot > -1.0 + 2.0 * BPE_ANGULAR_TOLERANCE:
                continue
            separation = max(
                abs(G.orientation(first, second, third)) / first_length,
                abs(G.orientation(first, second, fourth)) / first_length,
                abs(G.orientation(third, fourth, first)) / second_length,
                abs(G.orientation(third, fourth, second)) / second_length,
            )
            if separation <= BPE_SNAP_TOLERANCE + BPE_ENDPOINT_TOLERANCE:
                allowance += shared_length * separation
    return allowance * (1.0 + 1.0e-9)

def merge_polygons_at_edge(poly_a: list[dict], poly_b: list[dict], edge_a: tuple[dict, dict] = None, edge_b: tuple[dict, dict] = None) -> list[dict] | None:
    """Return the simple, area-conserving union of boundary-adjacent polygons.

    The two optional edge arguments remain accepted for API compatibility; the
    union intentionally examines *all* mutual boundary intervals so a shared
    wall split into several collinear pieces cannot leak into the result.

    The operation is fail-closed.  It splits both boundaries at every tolerant
    overlap endpoint, snaps corresponding endpoints, cancels each shared pair,
    and then requires every exposed segment to participate in exactly one
    closed loop.  Multiple loops (including a newly enclosed hole), incomplete
    chains, self-intersections, and any material area change return ``None``.
    Callers can therefore leave the original nodes untouched.
    """

    del edge_a, edge_b  # the complete boundary, not a guessed sub-edge, is authoritative
    tolerance = BPE_SNAP_TOLERANCE

    first_poly = _counter_clockwise_polygon(poly_a)
    second_poly = _counter_clockwise_polygon(poly_b)
    if not G.is_simple_polygon(first_poly) or not G.is_simple_polygon(second_poly):
        return None

    def split_boundary(poly: list[dict], other: list[dict], source: int) -> list[dict]:
        result = []
        for edge_index, start in enumerate(poly):
            end = poly[(edge_index + 1) % len(poly)]
            dx = end["x"] - start["x"]
            dy = end["y"] - start["y"]
            length_squared = dx * dx + dy * dy
            length = math.sqrt(length_squared)
            if length <= 1.0e-9:
                return []
            parameters = [0.0, 1.0]
            for other_index, other_start in enumerate(other):
                other_end = other[(other_index + 1) % len(other)]
                if not _segments_collinear(start, end, other_start, other_end, tolerance):
                    continue
                first_parameter = (
                    (other_start["x"] - start["x"]) * dx
                    + (other_start["y"] - start["y"]) * dy
                ) / length_squared
                second_parameter = (
                    (other_end["x"] - start["x"]) * dx
                    + (other_end["y"] - start["y"]) * dy
                ) / length_squared
                overlap_start = max(0.0, min(first_parameter, second_parameter))
                overlap_end = min(1.0, max(first_parameter, second_parameter))
                if (overlap_end - overlap_start) * length > 1.0e-9:
                    parameters.extend((overlap_start, overlap_end))

            parameters.sort()
            unique_parameters = []
            parameter_tolerance = min(
                0.25,
                BPE_ENDPOINT_TOLERANCE / max(length, BPE_ENDPOINT_TOLERANCE),
            )
            for parameter in parameters:
                parameter = max(0.0, min(1.0, parameter))
                if not unique_parameters or abs(parameter - unique_parameters[-1]) > parameter_tolerance:
                    unique_parameters.append(parameter)
                else:
                    unique_parameters[-1] = (unique_parameters[-1] + parameter) / 2.0

            for start_parameter, end_parameter in zip(unique_parameters, unique_parameters[1:]):
                if (end_parameter - start_parameter) * length <= 1.0e-9:
                    continue
                segment_start = {
                    "x": start["x"] + start_parameter * dx,
                    "y": start["y"] + start_parameter * dy,
                }
                segment_end = {
                    "x": start["x"] + end_parameter * dx,
                    "y": start["y"] + end_parameter * dy,
                }
                result.append({"start": segment_start, "end": segment_end, "source": source})
        return result

    segments = split_boundary(first_poly, second_poly, 0) + split_boundary(second_poly, first_poly, 1)
    if not segments:
        return None

    # Snap only topologically corresponding shared endpoints.  A global
    # distance cluster would incorrectly collapse a legitimate 5 mm tangential
    # overhang just because the perpendicular contact tolerance is 1 cm.
    endpoints = []
    endpoint_sources = []
    for segment in segments:
        endpoints.extend((segment["start"], segment["end"]))
        endpoint_sources.extend((segment["source"], segment["source"]))
    parents = list(range(len(endpoints)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(first_index: int, second_index: int) -> None:
        first_root = find(first_index)
        second_root = find(second_index)
        if first_root == second_root:
            return
        if first_root < second_root:
            parents[second_root] = first_root
        else:
            parents[first_root] = second_root

    # Preserve exact continuity within each source polygon.
    for first_index, first in enumerate(endpoints):
        for second_index in range(first_index + 1, len(endpoints)):
            if endpoint_sources[first_index] != endpoint_sources[second_index]:
                continue
            if distance(first, endpoints[second_index]) <= BPE_ENDPOINT_TOLERANCE:
                union(first_index, second_index)

    segment_lengths = [distance(segment["start"], segment["end"]) for segment in segments]
    shared_candidates = []
    for first_index, first_segment in enumerate(segments):
        if first_segment["source"] != 0:
            continue
        first_length = segment_lengths[first_index]
        first_dx = first_segment["end"]["x"] - first_segment["start"]["x"]
        first_dy = first_segment["end"]["y"] - first_segment["start"]["y"]
        for second_index, second_segment in enumerate(segments):
            if second_segment["source"] != 1:
                continue
            second_length = segment_lengths[second_index]
            measure = _symmetric_overlap_measure(
                first_segment["start"],
                first_segment["end"],
                second_segment["start"],
                second_segment["end"],
            )
            if measure is None:
                continue
            _, _, shared_length = measure
            if (
                first_length - shared_length > BPE_ENDPOINT_TOLERANCE
                or second_length - shared_length > BPE_ENDPOINT_TOLERANCE
            ):
                continue
            second_dx = second_segment["end"]["x"] - second_segment["start"]["x"]
            second_dy = second_segment["end"]["y"] - second_segment["start"]["y"]
            direction_dot = (
                first_dx * second_dx + first_dy * second_dy
            ) / (first_length * second_length)
            if direction_dot > -1.0 + 2.0 * BPE_ANGULAR_TOLERANCE:
                continue
            start_error = distance(first_segment["start"], second_segment["end"])
            end_error = distance(first_segment["end"], second_segment["start"])
            if max(start_error, end_error) > 2.0 * BPE_SNAP_TOLERANCE:
                continue
            shared_candidates.append(
                (max(start_error, end_error), first_index, second_index)
            )

    paired_segments = set()
    shared_pairs = []
    for _, first_index, second_index in sorted(shared_candidates):
        if first_index in paired_segments or second_index in paired_segments:
            continue
        paired_segments.update((first_index, second_index))
        shared_pairs.append((first_index, second_index))
        # CCW adjacent polygons traverse a shared wall in opposite directions.
        union(2 * first_index, 2 * second_index + 1)
        union(2 * first_index + 1, 2 * second_index)

    if not shared_pairs:
        return None

    cluster_members: dict[int, list[dict]] = defaultdict(list)
    for index, point in enumerate(endpoints):
        cluster_members[find(index)].append(point)
    representatives = {
        root: {
            "x": math.fsum(point["x"] for point in points) / len(points),
            "y": math.fsum(point["y"] for point in points) / len(points),
        }
        for root, points in cluster_members.items()
    }

    # A tolerance chain must not silently collapse a material boundary span.
    for root, points in cluster_members.items():
        representative = representatives[root]
        if any(distance(point, representative) > BPE_SNAP_TOLERANCE for point in points):
            return None

    exposed_segments = []
    for segment_index, segment in enumerate(segments):
        if segment_index in paired_segments:
            continue
        start_root = find(2 * segment_index)
        end_root = find(2 * segment_index + 1)
        if start_root == end_root:
            continue
        segment = dict(segment)
        segment["start_root"] = start_root
        segment["end_root"] = end_root
        exposed_segments.append(segment)

    if len(exposed_segments) < 3:
        return None

    outgoing: dict[int, list[dict]] = defaultdict(list)
    incoming: dict[int, list[dict]] = defaultdict(list)
    for segment in exposed_segments:
        outgoing[segment["start_root"]].append(segment)
        incoming[segment["end_root"]].append(segment)
    boundary_roots = set(outgoing) | set(incoming)
    if any(len(outgoing[root]) != 1 or len(incoming[root]) != 1 for root in boundary_roots):
        return None

    start_root = min(boundary_roots)
    current_root = start_root
    used_edges = set()
    merged_poly = []
    for _ in range(len(exposed_segments) + 1):
        if current_root == start_root and used_edges:
            break
        segment = outgoing[current_root][0]
        edge_identity = (segment["start_root"], segment["end_root"])
        if edge_identity in used_edges:
            return None
        used_edges.add(edge_identity)
        merged_poly.append(dict(representatives[current_root]))
        current_root = segment["end_root"]

    if current_root != start_root or len(used_edges) != len(exposed_segments):
        # A second loop is either a true hole or an unconsumed/flapping wall;
        # the current single-ring placement schema cannot represent it safely.
        return None

    merged_poly = simplify_polygon(merged_poly)
    if len(merged_poly) < 3 or not G.is_simple_polygon(merged_poly):
        return None
    if len(merged_poly) == 4 and not G.is_convex_polygon(merged_poly):
        return None
    if G.polygon_signed_area(merged_poly) < 0.0:
        merged_poly.reverse()

    expected_area = G.polygon_area(first_poly) + G.polygon_area(second_poly)
    merged_area = G.polygon_area(merged_poly)
    area_tolerance = _bounded_snap_area_tolerance(first_poly, second_poly)
    numeric_tolerance = max(
        BPE_AREA_ABS_TOLERANCE,
        expected_area * BPE_AREA_REL_TOLERANCE,
    )
    area_delta = merged_area - expected_area
    if area_delta < -numeric_tolerance or area_delta > area_tolerance:
        return None

    return merged_poly

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
    
    identity_material = "|".join(
        (pair_key.type_a, pair_key.type_b, pair_key.geometry_signature)
    )
    identity_digest = hashlib.sha256(identity_material.encode("utf-8")).hexdigest()[:16]
    # Keep the legacy M_round prefix for protocol compatibility, but do not
    # encode traversal round in identity.  The same canonical geometry must
    # retain the same token even when another frequent pair is merged first.
    type_id = f"M_round_{identity_digest}"
    name = f"Merged Module ({pair_key.type_a} + {pair_key.type_b})"
    
    # Collect components
    components = []
    for node in (node_a, node_b):
        if "components" in node and node["components"]:
            components.extend(node["components"])
        else:
            components.append(node)

    # Phase 1C Anti-Sprawl Constraints: limit component count, compactness, and aspect ratio
    if len(components) > 4:
        return None

    area = G.polygon_area(union_poly)
    perim = G.polygon_perimeter(union_poly)
    if perim > 1.0e-6:
        compactness = (4.0 * math.pi * area) / (perim * perim)
        if compactness < 0.15:
            return None

    xs = [p["x"] for p in union_poly]
    ys = [p["y"] for p in union_poly]
    if xs and ys:
        span_x = max(xs) - min(xs)
        span_y = max(ys) - min(ys)
        min_span = max(1.0e-5, min(span_x, span_y))
        aspect_ratio = max(span_x, span_y) / min_span
        if aspect_ratio > 8.5:
            return None

    return MergedModule(
        type_id=type_id,
        name=name,
        poly=union_poly,
        components=components,
        geometry_signature=pair_key.geometry_signature,
    )

def _replace_pair_in_graph(
    graph: LayoutGraph,
    conn: EdgeConnection,
    merged: MergedModule,
    prepared_union_poly: list[dict] | None = None,
) -> bool:
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
    
    local_union_poly = prepared_union_poly
    if local_union_poly is None:
        local_union_poly = merge_polygons_at_edge(
            node_a["poly"],
            node_b["poly"],
            edge_a,
            edge_b
        )
    
    if local_union_poly is None:
        # Geometry union failed — keep original shapes intact
        return False
    expected_area = G.polygon_area(node_a["poly"]) + G.polygon_area(node_b["poly"])
    actual_area = G.polygon_area(local_union_poly)
    area_tolerance = _bounded_snap_area_tolerance(node_a["poly"], node_b["poly"])
    numeric_tolerance = max(
        BPE_AREA_ABS_TOLERANCE,
        expected_area * BPE_AREA_REL_TOLERANCE,
    )
    area_delta = actual_area - expected_area
    if (
        not G.is_simple_polygon(local_union_poly)
        or area_delta < -numeric_tolerance
        or area_delta > area_tolerance
    ):
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


def _connection_order_key(item: tuple[int, EdgeConnection]) -> tuple:
    graph_index, connection = item
    first_id, second_id = sorted((connection.shape_id_a, connection.shape_id_b))
    return (
        graph_index,
        first_id,
        second_id,
        round(connection.overlap_start["x"], 9),
        round(connection.overlap_start["y"], 9),
        round(connection.overlap_end["x"], 9),
        round(connection.overlap_end["y"], 9),
    )


def _maximum_disjoint_instances(
    instances: Sequence[tuple[int, EdgeConnection]],
) -> list[tuple[int, EdgeConnection]]:
    """Choose a deterministic maximum set of node-disjoint pair occurrences.

    Each floor is a general (not necessarily bipartite) occurrence graph, so a
    greedy or bipartite augmenting matcher can miss odd-cycle blossoms.  The
    helper below uses Edmonds' maximum-cardinality blossom algorithm in
    polynomial time and deterministic sorted traversal order.
    """

    by_graph: dict[int, list[tuple[int, EdgeConnection]]] = defaultdict(list)
    for item in sorted(instances, key=_connection_order_key):
        by_graph[item[0]].append(item)

    selected = []
    for graph_index in sorted(by_graph):
        candidates = by_graph[graph_index]
        node_ids = set()
        indexed_edges = []
        for index, (_, connection) in enumerate(candidates):
            first_id = connection.shape_id_a
            second_id = connection.shape_id_b
            if first_id == second_id:
                continue
            node_ids.update((first_id, second_id))
            indexed_edges.append((first_id, second_id, index))
        best_indexes = _edmonds_maximum_matching(tuple(sorted(node_ids)), indexed_edges)
        selected.extend(candidates[index] for index in best_indexes)

    return selected


def _edmonds_maximum_matching(
    node_ids: Sequence[str],
    indexed_edges: Sequence[tuple[str, str, int]],
) -> tuple[int, ...]:
    """Return edge indexes for a deterministic maximum-cardinality matching.

    This is the classic unweighted Edmonds blossom search.  Its worst-case
    running time is polynomial (O(V^3)); sorted vertices and adjacency make the
    selected maximum stable across input insertion order.  Parallel occurrence
    edges, if ever supplied, deterministically use their smallest index.
    """

    ordered_nodes = tuple(sorted(set(node_ids)))
    size = len(ordered_nodes)
    if size < 2:
        return ()
    node_index = {node_id: index for index, node_id in enumerate(ordered_nodes)}
    edge_index_by_pair: dict[tuple[int, int], int] = {}
    for first_id, second_id, edge_index in indexed_edges:
        if first_id not in node_index or second_id not in node_index or first_id == second_id:
            continue
        first = node_index[first_id]
        second = node_index[second_id]
        pair = (min(first, second), max(first, second))
        edge_index_by_pair[pair] = min(edge_index, edge_index_by_pair.get(pair, edge_index))

    adjacency = [[] for _ in range(size)]
    for first, second in sorted(edge_index_by_pair):
        adjacency[first].append(second)
        adjacency[second].append(first)
    for neighbors in adjacency:
        neighbors.sort()

    match = [-1] * size
    parent = [-1] * size
    base = list(range(size))
    used = [False] * size
    blossom = [False] * size

    def lowest_common_ancestor(first: int, second: int) -> int:
        in_path = [False] * size
        while True:
            first = base[first]
            in_path[first] = True
            if match[first] == -1:
                break
            first = parent[match[first]]
        while True:
            second = base[second]
            if in_path[second]:
                return second
            second = parent[match[second]]

    def mark_blossom_path(vertex: int, common_base: int, child: int) -> None:
        while base[vertex] != common_base:
            blossom[base[vertex]] = True
            blossom[base[match[vertex]]] = True
            parent[vertex] = child
            child = match[vertex]
            vertex = parent[match[vertex]]

    def find_augmenting_path(root: int) -> bool:
        nonlocal parent, base, used, blossom
        parent = [-1] * size
        base = list(range(size))
        used = [False] * size
        queue = [root]
        used[root] = True
        cursor = 0
        while cursor < len(queue):
            vertex = queue[cursor]
            cursor += 1
            for neighbor in adjacency[vertex]:
                if base[vertex] == base[neighbor] or match[vertex] == neighbor:
                    continue
                if neighbor == root or (
                    match[neighbor] != -1 and parent[match[neighbor]] != -1
                ):
                    common_base = lowest_common_ancestor(vertex, neighbor)
                    blossom = [False] * size
                    mark_blossom_path(vertex, common_base, neighbor)
                    mark_blossom_path(neighbor, common_base, vertex)
                    for index in range(size):
                        if blossom[base[index]]:
                            base[index] = common_base
                            if not used[index]:
                                used[index] = True
                                queue.append(index)
                elif parent[neighbor] == -1:
                    parent[neighbor] = vertex
                    if match[neighbor] == -1:
                        current = neighbor
                        while current != -1:
                            previous = parent[current]
                            following = match[previous] if previous != -1 else -1
                            match[current] = previous
                            if previous != -1:
                                match[previous] = current
                            current = following
                        return True
                    matched_neighbor = match[neighbor]
                    used[matched_neighbor] = True
                    queue.append(matched_neighbor)
        return False

    for root in range(size):
        if match[root] == -1:
            find_augmenting_path(root)

    selected_indexes = []
    for first, second in enumerate(match):
        if second > first:
            selected_indexes.append(edge_index_by_pair[(first, second)])
    return tuple(sorted(selected_indexes))

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
    vocabulary: dict[str, MergedModule] = {}
    original_nodes = [dict(layout_graph.nodes) for layout_graph in layout_graphs]
    original_connections = [list(layout_graph.connections) for layout_graph in layout_graphs]
    initial_area = math.fsum(
        G.polygon_area(node["poly"])
        for layout_graph in layout_graphs
        for node in layout_graph.nodes.values()
    )
    rejected_geometry_count = 0
    applied_merge_instances = 0
    applied_rounds = 0
    snap_area_budget = 0.0

    for round_num in range(max_rounds):
        # 1. Re-extract current full-edge adjacencies on every round.
        all_connections: list[tuple[int, EdgeConnection]] = []
        for graph_idx, layout_graph in enumerate(layout_graphs):
            all_connections.extend(
                (graph_idx, connection)
                for connection in find_edge_connections(layout_graph)
            )
        if not all_connections:
            break

        # 2. Canonicalize globally, then count actual node-disjoint instances.
        raw_pair_instances: dict[MergePairKey, list[tuple[int, EdgeConnection]]] = defaultdict(list)
        for graph_idx, connection in all_connections:
            pair_key = canonicalize_merge_key(connection, layout_graphs[graph_idx])
            raw_pair_instances[pair_key].append((graph_idx, connection))
        pair_instances = {
            pair_key: _maximum_disjoint_instances(instances)
            for pair_key, instances in raw_pair_instances.items()
        }
        ranked_pairs = sorted(
            ((pair_key, len(instances)) for pair_key, instances in pair_instances.items()),
            key=lambda item: (
                -item[1],
                item[0].type_a,
                item[0].type_b,
                item[0].geometry_signature,
            ),
        )

        # 3. Validate a complete merge plan before mutating a live graph.
        best_merged: MergedModule | None = None
        best_prepared: list[tuple[int, EdgeConnection, list[dict], float]] = []
        best_temp_graphs: dict[int, LayoutGraph] = {}
        for pair_key, count in ranked_pairs:
            if count < min_frequency:
                break

            prepared = []
            for graph_idx, connection in pair_instances[pair_key]:
                current_graph = layout_graphs[graph_idx]
                node_a = current_graph.nodes.get(connection.shape_id_a)
                node_b = current_graph.nodes.get(connection.shape_id_b)
                if node_a is None or node_b is None:
                    continue
                union_poly = merge_polygons_at_edge(node_a["poly"], node_b["poly"])
                if union_poly is None:
                    rejected_geometry_count += 1
                    continue
                parent_area = G.polygon_area(node_a["poly"]) + G.polygon_area(node_b["poly"])
                area_adjustment = max(0.0, G.polygon_area(union_poly) - parent_area)
                prepared.append((graph_idx, connection, union_poly, area_adjustment))
            if len(prepared) < min_frequency:
                continue

            graph_idx, first_connection, _, _ = prepared[0]
            merged_candidate = _create_merged_module_from_edge(
                pair_key,
                first_connection,
                layout_graphs[graph_idx],
                round_num,
            )
            if merged_candidate is None:
                rejected_geometry_count += len(prepared)
                continue

            temporary_graphs = {
                affected_index: LayoutGraph(
                    nodes=dict(layout_graphs[affected_index].nodes),
                    connections=list(layout_graphs[affected_index].connections),
                    playground_id=layout_graphs[affected_index].playground_id,
                )
                for affected_index in {item[0] for item in prepared}
            }
            committed = True
            for prepared_graph_idx, prepared_connection, prepared_union, _ in prepared:
                if not _replace_pair_in_graph(
                    temporary_graphs[prepared_graph_idx],
                    prepared_connection,
                    merged_candidate,
                    prepared_union,
                ):
                    committed = False
                    break
            if not committed:
                rejected_geometry_count += len(prepared)
                continue

            best_merged = merged_candidate
            best_prepared = prepared
            best_temp_graphs = temporary_graphs
            break

        if best_merged is None:
            break

        # 4. Commit the already validated node maps as one transaction.
        for graph_idx, temporary in best_temp_graphs.items():
            layout_graphs[graph_idx].nodes = temporary.nodes
            refreshed = extract_layout_graph(
                list(temporary.nodes.values()),
                layout_graphs[graph_idx].playground_id,
            )
            layout_graphs[graph_idx].connections = refreshed.connections
        vocabulary[best_merged.type_id] = best_merged
        applied_merge_instances += len(best_prepared)
        applied_rounds += 1
        snap_area_budget += math.fsum(item[3] for item in best_prepared)
        if len(vocabulary) >= max_vocab_size:
            break

    # 5. Roll back final singleton tokens to their preserved basic components.
    global_shape_counts = Counter(
        node.get("shapeType", "")
        for layout_graph in layout_graphs
        for node in layout_graph.nodes.values()
    )
    for layout_graph in layout_graphs:
        nodes_to_unmerge = [
            node_id
            for node_id, node in layout_graph.nodes.items()
            if node.get("shapeType", "").startswith("M_round")
            and global_shape_counts[node.get("shapeType", "")] < 2
        ]
        for node_id in nodes_to_unmerge:
            node = layout_graph.nodes.pop(node_id)
            for component in node.get("components", []):
                layout_graph.nodes[component["id"]] = component
        refreshed = extract_layout_graph(
            list(layout_graph.nodes.values()),
            layout_graph.playground_id,
        )
        layout_graph.connections = refreshed.connections

    # Public vocabulary entries must be backed by at least two final tokens.
    final_shape_counts = Counter(
        node.get("shapeType", "")
        for layout_graph in layout_graphs
        for node in layout_graph.nodes.values()
    )
    vocabulary = {
        type_id: module
        for type_id, module in vocabulary.items()
        if final_shape_counts[type_id] >= 2
    }

    final_area = math.fsum(
        G.polygon_area(node["poly"])
        for layout_graph in layout_graphs
        for node in layout_graph.nodes.values()
    )
    numeric_area_tolerance = max(
        BPE_AREA_ABS_TOLERANCE,
        initial_area * BPE_AREA_REL_TOLERANCE,
    )
    area_tolerance = numeric_area_tolerance + snap_area_budget * (1.0 + 1.0e-9)
    final_area_delta = final_area - initial_area
    global_rollback = (
        final_area_delta < -numeric_area_tolerance
        or final_area_delta > area_tolerance
    )
    if global_rollback:
        # Last-resort invariant guard: cumulative adjustment may never exceed
        # the sum of the explicitly measured contact-snap strips.
        for graph_index, layout_graph in enumerate(layout_graphs):
            layout_graph.nodes = original_nodes[graph_index]
            layout_graph.connections = original_connections[graph_index]
        vocabulary = {}
        applied_merge_instances = 0
        applied_rounds = 0
        snap_area_budget = 0.0
        final_area = initial_area

    final_area_delta = final_area - initial_area

    total_placements = sum(len(layout_graph.nodes) for layout_graph in layout_graphs)
    unique_types = len({
        get_node_shape_type(node)
        for layout_graph in layout_graphs
        for node in layout_graph.nodes.values()
    })

    return list(vocabulary.values()), {
        "total_placements": total_placements,
        "unique_types": unique_types,
        "merge_rounds": applied_rounds,
        "merged_instances": applied_merge_instances,
        "rejected_geometry": rejected_geometry_count,
        "filled_area_before": initial_area,
        "filled_area_after": final_area,
        "filled_area_delta": final_area_delta,
        "snap_area_tolerance": area_tolerance,
        "area_conserved": (
            final_area_delta >= -numeric_area_tolerance
            and final_area_delta <= area_tolerance
        ),
        "global_rollback": global_rollback,
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
    rel_angle = int(round(((rot_b - rot_a) % 360) / 15.0) * 15) % 360
    geometry_signature = pair_geometry_signature(node_a, node_b)
    
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
            relative_angle=rel_angle,
            geometry_signature=geometry_signature,
        )
    else:
        return MergePairKey(
            type_a=type_b,
            type_b=type_a,
            canon_edge_a=port_id_b[1],
            canon_edge_b=port_id_a[1],
            relative_angle=(-rel_angle) % 360,
            geometry_signature=geometry_signature,
        )
