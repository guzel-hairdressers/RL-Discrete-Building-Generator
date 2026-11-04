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
        import random
        site_boundary=[(p["x"],p["y"]) if isinstance(p,dict) else p for p in site_boundary]
        nodes=[n for n in graph.nodes.values() if n.floor_index==floor_index]
        if not nodes:
            return self._generate_initial_seeds(site_boundary,site_pca_axes)
        # A reproducible continuous distribution, with motif translations mixed in.
        rng=random.Random(173+len(graph.nodes)*104729+floor_index)
        spans=[math.dist((graph.nodes[e.u].x,graph.nodes[e.u].y),
                         (graph.nodes[e.v].x,graph.nodes[e.v].y))
               for e in graph.edges_horiz if graph.nodes[e.u].floor_index==floor_index]
        scale=sum(spans)/len(spans) if spans else 2*self.min_seed_distance
        # Bounded proposal work, independent of the number of already proposed
        # points. A spatial index replaces repeated all-node distance scans.
        width=self.min_seed_distance
        buckets={}
        for node in nodes:
            key=(math.floor(node.x/width),math.floor(node.y/width))
            buckets.setdefault(key,[]).append(node)
        anchors=sorted(nodes,key=lambda n:(n.x,n.y));rng.shuffle(anchors)
        proposals=[];seen=set();target=max(48,4*max_proposals)
        for node in anchors:
            star=sorted(graph.star_graph_offsets(node.node_id))
            displacements=list(star)+[(-x,-y) for x,y in star]
            for motif in active_motif_bank or []:
                displacements.extend(motif.get('relative_offsets',[]))
            for _ in range(12):
                a=rng.uniform(0,2*math.pi);d=rng.uniform(.75,1.25)*scale
                displacements.append((math.cos(a)*d,math.sin(a)*d))
            for dx,dy in displacements:
                pt=(node.x+dx,node.y+dy)
                key=(round(pt[0],6),round(pt[1],6))
                if key in seen:continue
                seen.add(key)
                gx,gy=math.floor(pt[0]/width),math.floor(pt[1]/width)
                if any((pt[0]-n.x)**2+(pt[1]-n.y)**2<width*width
                       for ox in (-1,0,1) for oy in (-1,0,1)
                       for n in buckets.get((gx+ox,gy+oy),())):continue
                if not self._point_inside_polygon(pt,site_boundary,setback=self.site_setback):continue
                proposals.append(dict(x=pt[0],y=pt[1],anchor_node=node.node_id,
                    source='continuous_reference',span=math.hypot(dx,dy)))
                if len(proposals)>=target:break
            if len(proposals)>=target:break
        rng.shuffle(proposals)
        return proposals[:max_proposals]

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
        site_boundary: Sequence[dict | Sequence[float]] | list[tuple[float, float]],
        existing_nodes: Sequence[GraphNode] | None = None,
        bbox: tuple[float, float, float, float] | None = None,
    ) -> bool:
        """Check distance threshold and site boundary containment."""
        x, y = pt

        # 0. Fast O(1) bounding box check
        if bbox is not None:
            min_x, min_y, max_x, max_y = bbox
            sb = self.site_setback
            if x < min_x + sb or x > max_x - sb or y < min_y + sb or y > max_y - sb:
                return False

        # 1. Proximity check against existing nodes using squared distance
        if existing_nodes:
            min_dist_sq = self.min_seed_distance * self.min_seed_distance
            for en in existing_nodes:
                dx = x - en.x
                dy = y - en.y
                if (dx * dx + dy * dy) < min_dist_sq:
                    return False

        # 2. Proximity check against other candidate proposals (squared distance)
        sp_thresh_sq = (self.min_seed_distance * 0.4) ** 2
        for sp in seen_points:
            dx = x - sp[0]
            dy = y - sp[1]
            if (dx * dx + dy * dy) < sp_thresh_sq:
                return False

        # 3. Polygon containment with setback
        if site_boundary and isinstance(site_boundary[0], tuple):
            pts = site_boundary
        else:
            pts = [(float(p[0]), float(p[1])) if isinstance(p, (list, tuple)) else (float(p['x']), float(p['y'])) for p in site_boundary]
        return self._point_inside_polygon(pt, pts, setback=self.site_setback, bbox=bbox)

    @staticmethod
    def _point_inside_polygon(
        pt: tuple[float, float],
        polygon: list[tuple[float, float]],
        setback: float = 0.0,
        bbox: tuple[float, float, float, float] | None = None,
    ) -> bool:
        """Ray-casting point in polygon test with boundary clearance setback."""
        x, y = pt
        if bbox is not None:
            min_x, min_y, max_x, max_y = bbox
            if x < min_x + setback or x > max_x - setback or y < min_y + setback or y > max_y - setback:
                return False

        if polygon[0] != polygon[-1]:
            polygon = polygon + [polygon[0]]

        inside = False
        n = len(polygon)
        setback_sq = setback * setback

        for i in range(n - 1):
            x1, y1 = polygon[i]
            x2, y2 = polygon[i + 1]

            # Setback clearance check using squared distance
            dx = x2 - x1
            dy = y2 - y1
            l2 = dx * dx + dy * dy
            if l2 > 1e-9:
                t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / l2))
                px = x1 + t * dx
                py = y1 + t * dy
                dist_sq = (x - px) * (x - px) + (y - py) * (y - py)
                if dist_sq < setback_sq:
                    return False

            if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1) + x1):
                inside = not inside

        return inside


def convex_polygon_inside_site(polygon, boundary, tolerance=1e-8):
    """Containment without Boolean clipping, including concave site boundaries.

    Vertex inclusion alone misses a room edge spanning an exterior notch.
    Require included vertices and no proper room/site edge crossings.
    """
    if len(polygon)<3 or len(boundary)<3:return False
    site=[(float(p['x']),float(p['y'])) if isinstance(p,dict) else tuple(p) for p in boundary]
    if site[0]==site[-1]:site=site[:-1]
    def orient(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def covered(p):
        for a,b in zip(site,site[1:]+site[:1]):
            length=math.dist(a,b)
            if length and abs(orient(a,b,p))<=tolerance*length and min(a[0],b[0])-tolerance<=p[0]<=max(a[0],b[0])+tolerance and min(a[1],b[1])-tolerance<=p[1]<=max(a[1],b[1])+tolerance:
                return True
        return GraphSeedSampler._point_inside_polygon(p,site)
    if not all(covered(p) for p in polygon):return False
    for a,b in zip(polygon,polygon[1:]+polygon[:1]):
        for c,d in zip(site,site[1:]+site[:1]):
            o1,o2=orient(a,b,c),orient(a,b,d)
            o3,o4=orient(c,d,a),orient(c,d,b)
            if o1*o2 < -tolerance**2 and o3*o4 < -tolerance**2:return False
        if not covered(((a[0]+b[0])/2,(a[1]+b[1])/2)):return False
    return True
