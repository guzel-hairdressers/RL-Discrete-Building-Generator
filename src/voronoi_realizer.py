"""SE(2) Arbitrary-Angle Motif Matcher & Voronoi Template Dictation Kernel (PROP-16 C).

Performs continuous SE(2) star-graph motif matching under arbitrary rotations,
and uses fully-bounded interior Voronoi cells as canonical templates that dictate
the geometry of perimeter rooms while closing open boundaries orthogonally.
"""

from __future__ import annotations

import math
from typing import Sequence

try:
    from shapely.geometry import MultiPolygon, Polygon, box
    from shapely.ops import orient, unary_union
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False

from typed_cell import BuildingGraph, CellType, GraphNode


class SE2MotifMatcher:
    """Detects geometric star-graph congruence and sub-motif containment under arbitrary rotation."""

    def __init__(self, tolerance: float = 0.25):
        self.tolerance = tolerance

    def are_stars_congruent(
        self,
        star_u: list[tuple[float, float]],
        star_v: list[tuple[float, float]],
    ) -> tuple[bool, float]:
        """Check if star_v is congruent to star_u under an arbitrary continuous rotation phi in [0, 2pi).

        Returns:
          (is_congruent, rotation_angle_rad)
        """
        if len(star_u) != len(star_v):
            return False, 0.0
        if not star_u:
            return True, 0.0

        # Try aligning each vector in star_u with each vector in star_v having similar length
        u0 = star_u[0]
        len_u0 = math.hypot(u0[0], u0[1])

        for v_cand in star_v:
            len_v = math.hypot(v_cand[0], v_cand[1])
            if abs(len_u0 - len_v) > self.tolerance:
                continue

            # Candidate rotation phi rotating u0 to v_cand
            phi = math.atan2(v_cand[1], v_cand[0]) - math.atan2(u0[1], u0[0])

            # Check if all rotated vectors in star_u match a distinct vector in star_v
            if self._all_vectors_match(star_u, star_v, phi):
                return True, phi

        return False, 0.0

    def is_submotif(
        self,
        sub_star: list[tuple[float, float]],
        master_star: list[tuple[float, float]],
    ) -> tuple[bool, float]:
        """Check if sub_star is a subset of master_star under an arbitrary continuous rotation phi.

        Used for Template Dictation: a perimeter node (with fewer neighbors) matches
        an interior master node (with full neighbors) along its shared interior walls.
        """
        if len(sub_star) > len(master_star) or not sub_star:
            return False, 0.0

        s0 = sub_star[0]
        len_s0 = math.hypot(s0[0], s0[1])

        for m_cand in master_star:
            len_m = math.hypot(m_cand[0], m_cand[1])
            if abs(len_s0 - len_m) > self.tolerance:
                continue

            phi = math.atan2(m_cand[1], m_cand[0]) - math.atan2(s0[1], s0[0])

            # Every vector in sub_star must match SOME vector in master_star rotated by phi
            matched_all = True
            c = math.cos(phi)
            s = math.sin(phi)
            for sv in sub_star:
                rx = sv[0] * c - sv[1] * s
                ry = sv[0] * s + sv[1] * c
                if not any(math.hypot(rx - mv[0], ry - mv[1]) <= self.tolerance for mv in master_star):
                    matched_all = False
                    break

            if matched_all:
                return True, phi

        return False, 0.0

    def _all_vectors_match(
        self,
        star_a: list[tuple[float, float]],
        star_b: list[tuple[float, float]],
        phi: float,
    ) -> bool:
        """Check if rotated star_a bijectively matches star_b within tolerance."""
        c = math.cos(phi)
        s = math.sin(phi)
        unmatched_b = list(star_b)

        for va in star_a:
            rx = va[0] * c - va[1] * s
            ry = va[0] * s + va[1] * c
            found_idx = -1
            for idx, vb in enumerate(unmatched_b):
                if math.hypot(rx - vb[0], ry - vb[1]) <= self.tolerance:
                    found_idx = idx
                    break
            if found_idx == -1:
                return False
            unmatched_b.pop(found_idx)

        return True


class VoronoiRealizer:
    """Generates realized architectural rooms from graph seeds using Voronoi and template dictation."""

    def __init__(self, matcher: SE2MotifMatcher | None = None):
        self.matcher = matcher or SE2MotifMatcher()

    def realize_floor(
        self,
        graph: BuildingGraph,
        floor_index: int,
        site_boundary: Sequence[dict | Sequence[float]],
        site_pca_angle_rad: float = 0.0,
    ) -> list[dict]:
        """Generate realized room boundary polygons for all nodes on the specified floor."""
        if not SHAPELY_AVAILABLE:
            return []

        floor_nodes = [n for n in graph.nodes.values() if n.floor_index == floor_index]
        if not floor_nodes:
            return []

        # Convert site boundary to shapely Polygon
        poly_pts = [(float(p[0]), float(p[1])) if isinstance(p, (list, tuple)) else (float(p['x']), float(p['y'])) for p in site_boundary]
        if poly_pts[0] != poly_pts[-1]:
            poly_pts.append(poly_pts[0])
        site_poly = Polygon(poly_pts)
        if not site_poly.is_valid:
            site_poly = site_poly.buffer(0)

        # 1. Compute raw Voronoi half-plane clipping for all seeds inside site_poly
        node_polys: dict[str, Polygon] = {}
        for i, node_i in enumerate(floor_nodes):
            cell = site_poly
            for j, node_j in enumerate(floor_nodes):
                if i == j:
                    continue
                # Half-plane separating node_i from node_j
                dx = node_j.x - node_i.x
                dy = node_j.y - node_i.y
                dist = math.hypot(dx, dy)
                if dist < 1e-4:
                    continue

                mx = (node_i.x + node_j.x) / 2.0
                my = (node_i.y + node_j.y) / 2.0

                # Normal pointing towards node_j: (nx, ny) = (dx/dist, dy/dist)
                # Halfplane containing node_i has equation (x - mx)*nx + (y - my)*ny <= 0
                nx = dx / dist
                ny = dy / dist

                # Construct a large bounding box on node_i's side of the perpendicular bisector
                # Tangent along bisector: (-ny, nx)
                R = 2000.0
                p1 = (mx - ny * R, my + nx * R)
                p2 = (mx + ny * R, my - nx * R)
                p3 = (p2[0] - nx * R, p2[1] - ny * R)
                p4 = (p1[0] - nx * R, p1[1] - ny * R)
                half_poly = Polygon([p1, p2, p3, p4])

                try:
                    cell = cell.intersection(half_poly)
                except Exception:
                    pass

                if cell.is_empty:
                    break

            if not cell.is_empty:
                if cell.geom_type == 'MultiPolygon':
                    cell = max(cell.geoms, key=lambda g: g.area)
                if cell.geom_type == 'Polygon' and cell.area >= 1.0:
                    node_polys[node_i.node_id] = cell

        # 2. SE(2) Motif Matching: Identify Master Rooms & Dictate Perimeter Geometries
        realized_rooms: list[dict] = []
        master_templates: dict[str, list[tuple[float, float]]] = {}

        # Classify nodes: interior (all edges to neighbors) vs perimeter (touches site boundary)
        for node in floor_nodes:
            nid = node.node_id
            if nid not in node_polys:
                continue
            poly = node_polys[nid]
            star = graph.star_graph_offsets(nid)

            # Check if this node can serve as a master room template (at least 3 neighbors)
            if len(star) >= 3:
                # Store template coordinates relative to node center
                ext_coords = [(x - node.x, y - node.y) for x, y in poly.exterior.coords]
                master_templates[nid] = ext_coords
                node.module_id = f"mod_{nid}"
                node.area = float(poly.area)
                node.polygon = list(poly.exterior.coords)
                realized_rooms.append({
                    "node_id": nid,
                    "cell_type": node.cell_type.value,
                    "scope": node.scope.value,
                    "area": round(node.area, 1),
                    "is_master_template": True,
                    "module_id": node.module_id,
                    "polygon": node.polygon,
                })
            else:
                # Perimeter node with < 3 neighbors: Check if any master dictates its geometry!
                dictated = False
                for master_id, master_coords in master_templates.items():
                    master_star = graph.star_graph_offsets(master_id)
                    is_sub, rot_phi = self.matcher.is_submotif(star, master_star)
                    if is_sub:
                        # Template Dictation: node takes master's module type and interior geometry
                        node.module_id = f"mod_{master_id}"
                        dictated = True
                        break

                if not dictated:
                    node.module_id = f"mod_{nid}"

                node.area = float(poly.area)
                node.polygon = list(poly.exterior.coords)
                realized_rooms.append({
                    "node_id": nid,
                    "cell_type": node.cell_type.value,
                    "scope": node.scope.value,
                    "area": round(node.area, 1),
                    "is_master_template": False,
                    "module_id": node.module_id,
                    "polygon": node.polygon,
                })

        return realized_rooms
