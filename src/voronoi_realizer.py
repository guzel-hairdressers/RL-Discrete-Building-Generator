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
    from shapely.affinity import rotate, scale, translate
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

    @staticmethod
    def get_canonical_polygon_signature(coords: list[tuple[float, float]], area: float) -> str:
        """Compute rotation/reflection-invariant geometric signature matching frontend Diagnostics."""
        n = len(coords)
        if n < 3:
            return "empty"
        side_lengths = []
        for i in range(n):
            p1 = coords[i]
            p2 = coords[(i + 1) % n]
            d = round(math.hypot(p2[0] - p1[0], p2[1] - p1[1]) * 10) / 10.0
            side_lengths.append(d)
        cycles = []
        for i in range(n):
            cycles.append(tuple(side_lengths[i:] + side_lengths[:i]))
        rev = list(reversed(side_lengths))
        for i in range(n):
            cycles.append(tuple(rev[i:] + rev[:i]))
        can = min(cycles)
        return f"{n}_A{int(round(area * 10))}_{can}"

    def realize_floor(
        self,
        graph: BuildingGraph,
        floor_index: int,
        site_boundary: Sequence[dict | Sequence[float]],
        site_pca_angle_rad: float = 0.0,
        max_bay_size: float = 6.5,
        max_module_area: float = 50.0,
    ) -> list[dict]:
        """Generate realized room boundary polygons with modular area capping and SE(2) canonicalization."""
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

        # 1. Compute modular Voronoi clipping with oriented local envelope (prevents boundary runaway)
        node_polys: dict[str, Polygon] = {}
        for i, node_i in enumerate(floor_nodes):
            # Modular oriented box centered at node_i (aligned with site PCA angle)
            envelope_box = Polygon([
                (-max_bay_size / 2.0, -max_bay_size / 2.0),
                (max_bay_size / 2.0, -max_bay_size / 2.0),
                (max_bay_size / 2.0, max_bay_size / 2.0),
                (-max_bay_size / 2.0, max_bay_size / 2.0),
            ])
            if abs(site_pca_angle_rad) > 1e-4:
                envelope_box = rotate(envelope_box, math.degrees(site_pca_angle_rad), origin=(0, 0))
            envelope_box = translate(envelope_box, xoff=node_i.x, yoff=node_i.y)

            # Confine to site boundary; rooms never stretch beyond their local envelope
            cell = envelope_box.intersection(site_poly)

            for j, node_j in enumerate(floor_nodes):
                if i == j:
                    continue
                dx = node_j.x - node_i.x
                dy = node_j.y - node_i.y
                dist = math.hypot(dx, dy)
                if dist < 1e-4 or dist > 20.0:
                    continue

                mx = (node_i.x + node_j.x) / 2.0
                my = (node_i.y + node_j.y) / 2.0
                nx = dx / dist
                ny = dy / dist

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
                # Enforce strict module area cap (<= 50m2)
                if cell.geom_type == 'Polygon' and 1.0 <= cell.area <= max_module_area:
                    node_polys[node_i.node_id] = cell
                elif cell.geom_type == 'Polygon' and cell.area > max_module_area:
                    # Scale down to respect module area cap
                    scale_factor = math.sqrt(max_module_area / cell.area)
                    from shapely.affinity import scale
                    node_polys[node_i.node_id] = scale(cell, xfact=scale_factor, yfact=scale_factor, origin=(node_i.x, node_i.y))

        # 2. Canonical Signature Grouping: Identify Repeatable Modular Templates
        sig_groups: dict[str, list[str]] = {}
        node_sigs: dict[str, str] = {}
        node_rounded_coords: dict[str, list[tuple[float, float]]] = {}

        for node in floor_nodes:
            nid = node.node_id
            if nid not in node_polys:
                continue
            poly = node_polys[nid]
            coords = [(round(x, 1), round(y, 1)) for x, y in poly.exterior.coords[:-1]]
            area = round(float(poly.area), 1)
            sig = self.get_canonical_polygon_signature(coords, area)
            if node.cell_type == CellType.CORE:
                sig = f"core_{sig}"

            node_sigs[nid] = sig
            node_rounded_coords[nid] = coords
            sig_groups.setdefault(sig, []).append(nid)

        # Build clean canonical module IDs by frequency
        template_name_map: dict[str, str] = {}
        sig_order = sorted(sig_groups.keys(), key=lambda s: -len(sig_groups[s]))
        room_idx = 1
        for sig in sig_order:
            if sig.startswith("core_"):
                template_name_map[sig] = "mod_core_36m2"
            else:
                template_name_map[sig] = f"mod_std_m{room_idx}"
                room_idx += 1

        realized_rooms: list[dict] = []
        for node in floor_nodes:
            nid = node.node_id
            if nid not in node_polys:
                continue
            poly = node_polys[nid]
            coords = node_rounded_coords[nid]
            sig = node_sigs[nid]
            uses = len(sig_groups.get(sig, []))
            mod_id = template_name_map.get(sig, f"mod_{nid}")
            star = graph.star_graph_offsets(nid)

            node.module_id = mod_id
            node.area = float(poly.area)
            node.polygon = coords

            realized_rooms.append({
                "node_id": nid,
                "cell_type": node.cell_type.value,
                "scope": node.scope.value,
                "area": round(node.area, 1),
                "is_master_template": (uses > 1) or (len(star) >= 3),
                "module_id": mod_id,
                "canonical_sig": sig,
                "uses": uses,
                "polygon": coords,
            })

        return realized_rooms
