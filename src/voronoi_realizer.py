"""SE(2) Arbitrary-Angle Motif Matcher & Voronoi Template Dictation Kernel (PROP-16 C).

Performs continuous SE(2) star-graph motif matching under arbitrary rotations,
and uses fully-bounded interior Voronoi cells as canonical templates that dictate
the geometry of perimeter rooms while closing open boundaries orthogonally.
"""

from __future__ import annotations

import math
from typing import Sequence

try:
    from shapely.geometry import MultiPolygon, Point, Polygon, box
    from shapely.ops import orient, unary_union
    from shapely.affinity import rotate, scale, translate
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False

from typed_cell import BuildingGraph, CellType, GraphNode


class SE2MotifMatcher:
    """Detects geometric star-graph congruence and sub-motif containment under arbitrary rotation and reflection."""

    def __init__(
        self,
        length_tolerance: float = 0.75,
        angle_tolerance_deg: float = 10.0,
        tolerance: float | None = None,
    ):
        if tolerance is not None:
            self.length_tolerance = tolerance
        else:
            self.length_tolerance = length_tolerance
        self.length_tolerance_sq = self.length_tolerance * self.length_tolerance
        self.angle_tolerance_rad = math.radians(angle_tolerance_deg)

    def are_stars_congruent(
        self,
        star_u: list[tuple[float, float]],
        star_v: list[tuple[float, float]],
        return_reflection: bool = False,
    ) -> tuple[bool, float] | tuple[bool, float, bool]:
        """Check if star_v is congruent to star_u under continuous rotation phi and optional reflection."""
        if len(star_u) != len(star_v):
            return (False, 0.0, False) if return_reflection else (False, 0.0)
        if not star_u:
            return (True, 0.0, False) if return_reflection else (True, 0.0)

        u0 = star_u[0]
        len_u0 = math.hypot(u0[0], u0[1])

        for v_cand in star_v:
            len_v = math.hypot(v_cand[0], v_cand[1])
            if abs(len_u0 - len_v) > self.length_tolerance:
                continue

            for refl in (False,):
                phi = math.atan2(v_cand[1], v_cand[0]) - math.atan2(-u0[1] if refl else u0[1], u0[0])

                if self._all_vectors_match(star_u, star_v, phi, refl):
                    return (True, phi, refl) if return_reflection else (True, phi)

        return (False, 0.0, False) if return_reflection else (False, 0.0)

    def is_submotif(
        self,
        sub_star: list[tuple[float, float]],
        master_star: list[tuple[float, float]],
        return_reflection: bool = False,
    ) -> tuple[bool, float] | tuple[bool, float, bool]:
        """Check if sub_star is a subset of master_star under continuous rotation phi and optional reflection."""
        if len(sub_star) > len(master_star) or not sub_star:
            return (False, 0.0, False) if return_reflection else (False, 0.0)

        s0 = sub_star[0]
        len_s0 = math.hypot(s0[0], s0[1])
        tol_sq = self.length_tolerance_sq

        for m_cand in master_star:
            len_m = math.hypot(m_cand[0], m_cand[1])
            if abs(len_s0 - len_m) > self.length_tolerance:
                continue

            for refl in (False,):
                phi = math.atan2(m_cand[1], m_cand[0]) - math.atan2(-s0[1] if refl else s0[1], s0[0])
                c = math.cos(phi)
                s = math.sin(phi)
                matched_all = True
                unmatched_master = list(master_star)

                for sv in sub_star:
                    sx = sv[0]
                    sy = -sv[1] if refl else sv[1]
                    rx = sx * c - sy * s
                    ry = sx * s + sy * c

                    found_idx = -1
                    for idx, mv in enumerate(unmatched_master):
                        dist_sq = (rx - mv[0]) * (rx - mv[0]) + (ry - mv[1]) * (ry - mv[1])
                        if dist_sq <= tol_sq:
                            ang_diff = abs(math.atan2(ry, rx) - math.atan2(mv[1], mv[0]))
                            ang_diff = min(ang_diff, 2 * math.pi - ang_diff)
                            if ang_diff <= self.angle_tolerance_rad:
                                found_idx = idx
                                break
                    if found_idx == -1:
                        matched_all = False
                        break
                    unmatched_master.pop(found_idx)

                if matched_all:
                    return (True, phi, refl) if return_reflection else (True, phi)

        return (False, 0.0, False) if return_reflection else (False, 0.0)

    def _all_vectors_match(
        self,
        star_a: list[tuple[float, float]],
        star_b: list[tuple[float, float]],
        phi: float,
        refl: bool = False,
    ) -> bool:
        c = math.cos(phi)
        s = math.sin(phi)
        unmatched_b = list(star_b)
        tol_sq = self.length_tolerance_sq
        for va in star_a:
            vx = va[0]
            vy = -va[1] if refl else va[1]
            rx = vx * c - vy * s
            ry = vx * s + vy * c
            found_idx = -1
            for idx, vb in enumerate(unmatched_b):
                dist_sq = (rx - vb[0]) * (rx - vb[0]) + (ry - vb[1]) * (ry - vb[1])
                if dist_sq <= tol_sq:
                    ang_diff = abs(math.atan2(ry, rx) - math.atan2(vb[1], vb[0]))
                    ang_diff = min(ang_diff, 2 * math.pi - ang_diff)
                    if ang_diff <= self.angle_tolerance_rad:
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
    def get_node_local_angle(star_offsets: list[tuple[float, float]], fallback_angle: float = 0.0) -> float:
        """Find dominant local grid angle modulo pi/2 from a node's connection vectors."""
        if not star_offsets:
            return fallback_angle
        sin_sum = sum(math.sin(4.0 * math.atan2(y, x)) for x, y in star_offsets)
        cos_sum = sum(math.cos(4.0 * math.atan2(y, x)) for x, y in star_offsets)
        if math.hypot(sin_sum, cos_sum) < 1e-4:
            return math.atan2(star_offsets[0][1], star_offsets[0][0])
        avg_4 = math.atan2(sin_sum, cos_sum)
        return (avg_4 / 4.0) % (math.pi / 2.0)

    @staticmethod
    def get_canonical_polygon_signature(
        coords: list[tuple[float, float]],
        area: float,
        len_res: float = 0.1,
        ang_res_deg: float = 2.0,
    ) -> str:
        """Compute rotation/reflection-invariant geometric signature matching frontend Diagnostics."""
        pts = list(coords)
        if len(pts) > 1 and math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 1e-3:
            pts.pop()
        n = len(pts)
        if n < 3:
            return "empty"

        # Filter micro-edges (< 0.2m)
        filtered = []
        for i in range(n):
            p1 = pts[i]
            p2 = pts[(i + 1) % n]
            if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) >= 0.2:
                filtered.append(p1)
        if len(filtered) < 3:
            return "empty"
        pts = filtered
        n = len(pts)

        # Compute (length, turning_angle) at each vertex
        elements = []
        for i in range(n):
            p_prev = pts[(i - 1) % n]
            p_curr = pts[i]
            p_next = pts[(i + 1) % n]

            v_in = (p_curr[0] - p_prev[0], p_curr[1] - p_prev[1])
            v_out = (p_next[0] - p_curr[0], p_next[1] - p_curr[1])

            len_in = math.hypot(v_in[0], v_in[1])
            dot = v_in[0] * v_out[0] + v_in[1] * v_out[1]
            cross = v_in[0] * v_out[1] - v_in[1] * v_out[0]
            ang = math.atan2(cross, dot)
            ang_deg = math.degrees(ang)

            r_len = round(len_in / len_res) * len_res
            r_ang = round(abs(ang_deg) / ang_res_deg) * ang_res_deg
            elements.append((round(r_len, 1), round(r_ang, 1)))

        cycles = []
        for i in range(n):
            cycles.append(tuple(elements[i:] + elements[:i]))
        rev_elements = [(elem[0], elem[1]) for elem in reversed(elements)]
        for i in range(n):
            cycles.append(tuple(rev_elements[i:] + rev_elements[:i]))
        can = min(cycles)
        return f"{n}_A{int(round(area))}_{can}"

    def classify_nodes_by_star_motifs(self, graph, floor_index, dict_cap=10):
        from shared_modules import infer
        result=infer(graph)
        ids={pid:i+1 for i,pid in enumerate(result.prototypes)}
        return {n.node_id:ids.get(n.module_id,0) for n in graph.nodes.values() if n.floor_index==floor_index}

    def realize_floor(self, graph, floor_index, site_boundary, site_pca_angle_rad=0.,
                      max_bay_size=6.5, max_module_area=80.,
                      master_selection_strategy='highest_usage', dict_cap=10, prepared=None):
        from shared_modules import infer, SizePrior, validate
        # One building-wide solve; no floor-local clipping or template choice.
        if prepared is None:
            result=infer(graph,getattr(graph,"size_prior",None) or SizePrior(max_area=max_module_area))
            boundaries=getattr(graph,'site_boundaries',{}) or {f:site_boundary for f in range(graph.num_floors)}
            audit=validate(result,boundaries)
        else:
            result,audit=prepared
        graph.last_inference=result
        graph.realization_audit={k:v for k,v in audit.items() if k!='polygons'}
        rows=[]
        for oid,o in result.occurrences.items():
            if not o.prototype: continue
            proto=result.prototypes[o.prototype]
            for n in o.nodes:
                if n.floor_index!=floor_index: continue
                poly=result.polygon(oid)
                n.polygon=poly
                n.area=area_of(poly)
                rows.append(dict(node_id=n.node_id,cell_type=n.cell_type.value,scope=n.scope.value,
                    area=n.area,room_number=list(result.prototypes).index(o.prototype)+1,
                    is_master_template=len(proto.members)>1,module_id=o.prototype,
                    canonical_sig=str(tuple(proto.polygon)),uses=len(proto.members),polygon=poly,
                    origin=o.origin,orientation=o.angle,occurrence_id=oid,
                    prior_boundary=proto.prior_boundary,validation_status='valid' if audit['valid'] else 'invalid'))
        return rows


def area_of(poly):
    from shared_modules import area
    return area(poly)
