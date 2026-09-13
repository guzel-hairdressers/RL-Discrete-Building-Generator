"""Frontier-Relative & Motif-Aware Seed Point Sampler (PROP-16 A).

Generates candidate seed proposals that enable genuine architectural repetition,
diagonal spans (e.g. sqrt(5)), polygon closures, and motif stamping, rather than
chaotic uniform scatter.
"""

from __future__ import annotations

import math
from typing import Sequence

from typed_cell import BuildingGraph, CellType, GraphNode


class GraphSeedSampler:
    """Proposes candidate seed points for expanding the building graph."""

    def __init__(
        self,
        default_bay_depths: Sequence[float] = (3.0, 6.0, 9.0),
        min_seed_distance: float = 2.5,
        site_setback: float = 1.0,
    ):
        self.default_bay_depths = list(default_bay_depths)
        self.min_seed_distance = min_seed_distance
        self.site_setback = site_setback

    def generate_candidates(
        self,
        graph: BuildingGraph,
        floor_index: int,
        site_boundary: Sequence[dict | Sequence[float]],
        site_pca_axes: tuple[tuple[float, float], tuple[float, float]] | None = None,
        active_motif_bank: list[dict] | None = None,
        max_proposals: int = 36,
    ) -> list[dict]:
        """Generate a structured pool of candidate seed positions."""
        existing_nodes = [n for n in graph.nodes.values() if n.floor_index == floor_index]
        candidates: list[dict] = []
        seen_points: list[tuple[float, float]] = [(n.x, n.y) for n in existing_nodes]

        # Case 1: Initial seed placement if floor is currently empty
        if not existing_nodes:
            return self._generate_initial_seeds(site_boundary, site_pca_axes)

        # Case 2: Frontier-Relative Vector Propagation (preserves non-modular spans like sqrt(5))
        frontier_edges = self._extract_frontier_edges(graph, floor_index)

        # Propose from all existing nodes along site PCA axes and diagonal modular spans
        axes = site_pca_axes or (((1.0, 0.0), (0.0, 1.0)))
        u_axis, v_axis = axes[0], axes[1]
        for node in existing_nodes:
            # Orthogonal bay propagation along principal axes
            for axis, a_tag in [(u_axis, "pca_axis_u"), (v_axis, "pca_axis_v")]:
                for dist in self.default_bay_depths:
                    for s in (1.0, -1.0):
                        c_pt = (node.x + axis[0] * s * dist, node.y + axis[1] * s * dist)
                        if self._is_valid_candidate(c_pt, seen_points, site_boundary, existing_nodes):
                            seen_points.append(c_pt)
                            candidates.append({
                                "x": round(c_pt[0], 2),
                                "y": round(c_pt[1], 2),
                                "anchor_node": node.node_id,
                                "source": "radial_pca_expansion",
                                "tag": a_tag,
                                "span": dist,
                            })

            # Diagonal span sampling: sqrt(5) (3m x 6m) and sqrt(2) (3m x 3m / 6m x 6m)
            for su in (1.0, -1.0):
                for sv in (1.0, -1.0):
                    # 3m x 6m diagonal -> sqrt(3^2 + 6^2) = 3*sqrt(5) ~ 6.71m
                    c_diag_sqrt5 = (
                        node.x + u_axis[0] * su * 6.0 + v_axis[0] * sv * 3.0,
                        node.y + u_axis[1] * su * 6.0 + v_axis[1] * sv * 3.0,
                    )
                    if self._is_valid_candidate(c_diag_sqrt5, seen_points, site_boundary, existing_nodes):
                        seen_points.append(c_diag_sqrt5)
                        candidates.append({
                            "x": round(c_diag_sqrt5[0], 2),
                            "y": round(c_diag_sqrt5[1], 2),
                            "anchor_node": node.node_id,
                            "source": "vector_propagation",
                            "tag": "diagonal_bay_sqrt5",
                            "span": math.sqrt(45.0),
                        })

        for u_id, v_id in frontier_edges:
            u_node = graph.nodes[u_id]
            v_node = graph.nodes[v_id]
            dx = v_node.x - u_node.x
            dy = v_node.y - u_node.y
            edge_len = math.hypot(dx, dy)
            if edge_len < 1e-3:
                continue

            # Unit normal pointing outward (two sides)
            nx = -dy / edge_len
            ny = dx / edge_len

            # Test both outward and inward normals
            for sign in (1.0, -1.0):
                curr_nx = nx * sign
                curr_ny = ny * sign

                # Propose bay extensions using standard depths and edge-proportional depth
                depths = list(self.default_bay_depths)
                if abs(edge_len - 3.0) > 0.5 and abs(edge_len - 6.0) > 0.5:
                    depths.append(edge_len)  # Preserve custom/diagonal span aspect

                for depth in depths:
                    # Offset parallel edge points
                    c1 = (u_node.x + curr_nx * depth, u_node.y + curr_ny * depth)
                    c2 = (v_node.x + curr_nx * depth, v_node.y + curr_ny * depth)
                    c_mid = ((c1[0] + c2[0]) / 2.0, (c1[1] + c2[1]) / 2.0)

                    for pt, tag in [(c_mid, "bay_center"), (c1, "bay_corner_u"), (c2, "bay_corner_v")]:
                        if self._is_valid_candidate(pt, seen_points, site_boundary, existing_nodes):
                            seen_points.append(pt)
                            candidates.append({
                                "x": round(pt[0], 2),
                                "y": round(pt[1], 2),
                                "anchor_node": u_id,
                                "anchor_edge": (u_id, v_id),
                                "source": "vector_propagation",
                                "tag": tag,
                                "span": edge_len,
                            })

        # Case 3: Polygon Closures (Triangles with sqrt(5), sqrt(2), equilateral apexes)
        for u_id, v_id in frontier_edges:
            u = graph.nodes[u_id]
            v = graph.nodes[v_id]
            dx = v.x - u.x
            dy = v.y - u.y
            L = math.hypot(dx, dy)
            if L < 1e-3:
                continue

            # 3A. Triangle Apex Closures (equilateral and 45-deg apexes)
            mx = (u.x + v.x) / 2.0
            my = (u.y + v.y) / 2.0
            for h_factor, tag in [(0.5, "half_span_apex"), (math.sqrt(3.0) / 2.0, "equilateral_apex"), (1.0, "full_span_apex")]:
                h = L * h_factor
                for s in (1.0, -1.0):
                    c_apex = (mx - (dy / L) * s * h, my + (dx / L) * s * h)
                    if self._is_valid_candidate(c_apex, seen_points, site_boundary, existing_nodes):
                        seen_points.append(c_apex)
                        candidates.append({
                            "x": round(c_apex[0], 2),
                            "y": round(c_apex[1], 2),
                            "anchor_node": u_id,
                            "anchor_edge": (u_id, v_id),
                            "source": "polygon_closure",
                            "tag": tag,
                            "span": math.hypot(c_apex[0] - u.x, c_apex[1] - u.y),
                        })

        # Case 4: Active Motif Stamping
        if active_motif_bank:
            for motif in active_motif_bank:
                offsets = motif.get("relative_offsets", [])
                for node in existing_nodes:
                    for ox, oy in offsets:
                        pt = (node.x + ox, node.y + oy)
                        if self._is_valid_candidate(pt, seen_points, site_boundary, existing_nodes):
                            seen_points.append(pt)
                            candidates.append({
                                "x": round(pt[0], 2),
                                "y": round(pt[1], 2),
                                "anchor_node": node.node_id,
                                "source": "motif_stamp",
                                "motif_id": motif.get("id"),
                            })

        # Rank candidates for compact, balanced 2D expansion around site centroid / core
        pts = [(float(p[0]), float(p[1])) if isinstance(p, (list, tuple)) else (float(p['x']), float(p['y'])) for p in site_boundary]
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)

        def candidate_score(c: dict) -> float:
            dist_center = math.hypot(c["x"] - cx, c["y"] - cy)
            local_support = sum(
                1 for en in existing_nodes if math.hypot(c["x"] - en.x, c["y"] - en.y) <= 7.0
            )
            # Prefer compact growth close to center and well-supported by existing structure
            return dist_center - (local_support * 2.5)

        candidates.sort(key=candidate_score)
        return candidates[:max_proposals]

    def _generate_initial_seeds(
        self,
        site_boundary: Sequence[dict | Sequence[float]],
        site_pca_axes: tuple[tuple[float, float], tuple[float, float]] | None,
    ) -> list[dict]:
        """Propose central seed candidates for the initial placement on an empty site."""
        pts = [(float(p[0]), float(p[1])) if isinstance(p, (list, tuple)) else (float(p['x']), float(p['y'])) for p in site_boundary]
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)

        candidates = [{"x": cx, "y": cy, "source": "site_centroid", "tag": "core_seed"}]

        if site_pca_axes:
            u_axis, v_axis = site_pca_axes
            for dist in (6.0, 12.0):
                for s in (1.0, -1.0):
                    p_u = (cx + u_axis[0] * s * dist, cy + u_axis[1] * s * dist)
                    p_v = (cx + v_axis[0] * s * dist, cy + v_axis[1] * s * dist)
                    if self._point_inside_polygon(p_u, pts, setback=self.site_setback):
                        candidates.append({"x": p_u[0], "y": p_u[1], "source": "pca_axis_u", "span": dist})
                    if self._point_inside_polygon(p_v, pts, setback=self.site_setback):
                        candidates.append({"x": p_v[0], "y": p_v[1], "source": "pca_axis_v", "span": dist})

        return candidates

    def _extract_frontier_edges(self, graph: BuildingGraph, floor_index: int) -> list[tuple[str, str]]:
        """Identify edges on the boundary/frontier of the floor's graph."""
        floor_nodes = {n.node_id for n in graph.nodes.values() if n.floor_index == floor_index}
        frontier: list[tuple[str, str]] = []

        for edge in graph.edges_horiz:
            if edge.u in floor_nodes and edge.v in floor_nodes:
                frontier.append((edge.u, edge.v))

        # If graph has isolated nodes with no edges, form virtual frontier to nearest neighbors
        if not frontier and floor_nodes:
            nodes_list = [graph.nodes[nid] for nid in floor_nodes]
            for i in range(len(nodes_list)):
                for j in range(i + 1, len(nodes_list)):
                    frontier.append((nodes_list[i].node_id, nodes_list[j].node_id))

        return frontier

    def _is_valid_candidate(
        self,
        pt: tuple[float, float],
        seen_points: list[tuple[float, float]],
        site_boundary: Sequence[dict | Sequence[float]],
        existing_nodes: Sequence[GraphNode] | None = None,
    ) -> bool:
        """Check distance threshold and site boundary containment."""
        # 1. Proximity check against existing nodes
        if existing_nodes:
            for en in existing_nodes:
                if math.hypot(pt[0] - en.x, pt[1] - en.y) < self.min_seed_distance:
                    return False

        # 2. Proximity check against other candidate proposals (smaller threshold to allow diverse choices)
        for sp in seen_points:
            if math.hypot(pt[0] - sp[0], pt[1] - sp[1]) < (self.min_seed_distance * 0.4):
                return False

        # 3. Polygon containment with setback
        pts = [(float(p[0]), float(p[1])) if isinstance(p, (list, tuple)) else (float(p['x']), float(p['y'])) for p in site_boundary]
        return self._point_inside_polygon(pt, pts, setback=self.site_setback)

    @staticmethod
    def _point_inside_polygon(
        pt: tuple[float, float],
        polygon: list[tuple[float, float]],
        setback: float = 0.0,
    ) -> bool:
        """Ray-casting point in polygon test with boundary clearance setback."""
        if polygon[0] != polygon[-1]:
            polygon = polygon + [polygon[0]]

        x, y = pt
        inside = False
        n = len(polygon)

        for i in range(n - 1):
            x1, y1 = polygon[i]
            x2, y2 = polygon[i + 1]

            # Setback clearance check
            dx = x2 - x1
            dy = y2 - y1
            l2 = dx * dx + dy * dy
            if l2 > 1e-9:
                t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / l2))
                dist = math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))
                if dist < setback:
                    return False

            if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1) + x1):
                inside = not inside

        return inside
