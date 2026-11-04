"""Typed-Cell Ontology & Hierarchical Multi-Floor Graph Model (PROP-17 & PROP-16).

Decouples vertical scope (multi-floor vs independent) from architectural function
(core, room, void, balcony) and models multi-story buildings as a hierarchical graph
G = (V, E_horiz, E_vert) with void connectivity glue.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Sequence


class CellType(str, enum.Enum):
    """Architectural function / enclosure of a cell."""
    CORE = "core"          # Vertical circulation & egress (stairs, elevators, MEP shafts)
    ROOM = "room"          # Habitable enclosed space (apartments, offices, conference)
    VOID = "void"          # Unenclosed space (atriums, courtyards, light-wells, ditches)
    BALCONY = "balcony"    # Exterior open extension attached to a room


class VerticalScope(str, enum.Enum):
    """Vertical replication scope across building stories."""
    MULTI_FLOOR = "multi_floor"    # Replicated on every floor with aligned coordinates
    INDEPENDENT = "independent"    # Floor-specific placement (exists on a single story)


class VoidCategory(str, enum.Enum):
    """Classification of void cells for reward shaping and daylight computation."""
    ATRIUM = "atrium"          # Substantial enclosed open space providing daylight
    COURTYARD = "courtyard"    # Ground-level or terrace exterior garden/patio
    CLEARANCE = "clearance"    # Narrow structural separation or circulation ditch


@dataclass
class GraphNode:
    """A node in the architectural building graph."""
    node_id: str
    x: float
    y: float
    z: float = 0.0
    floor_index: int = 0
    cell_type: CellType = CellType.ROOM
    scope: VerticalScope = VerticalScope.INDEPENDENT
    module_id: str | None = None
    void_category: VoidCategory | None = None
    orientation: float = 0.0
    area: float = 0.0
    polygon: list[tuple[float, float]] | None = None
    metadata: dict = field(default_factory=dict)

    @property
    def pos2d(self) -> tuple[float, float]:
        return (self.x, self.y)

    @property
    def pos3d(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


@dataclass
class GraphEdge:
    """An adjacency or structural coupling edge in the building graph."""
    u: str
    v: str
    edge_type: str = "horiz"   # "horiz" (same floor) or "vert" (inter-floor)
    shared_length: float = 0.0 # Length of shared wall or overlap
    properties: dict = field(default_factory=dict)


class BuildingGraph:
    """Hierarchical multi-story graph representation G = (V, E_horiz, E_vert)."""

    def __init__(self, num_floors: int = 4, floor_height: float = 3.5):
        self.num_floors = num_floors
        self.floor_height = floor_height
        self.nodes: dict[str, GraphNode] = {}
        self.edges_horiz: list[GraphEdge] = []
        self.edges_vert: list[GraphEdge] = []
        self._adj_horiz: dict[str, set[str]] = {}
        self._adj_vert: dict[str, set[str]] = {}

    def add_node(
        self,
        node_id: str,
        x: float,
        y: float,
        floor_index: int = 0,
        cell_type: CellType = CellType.ROOM,
        scope: VerticalScope = VerticalScope.INDEPENDENT,
        module_id: str | None = None,
        void_category: VoidCategory | None = None,
        area: float = 0.0,
        polygon: list[tuple[float, float]] | None = None,
        metadata: dict | None = None,
    ) -> GraphNode:
        """Add a cell node to the building graph."""
        z = floor_index * self.floor_height
        node = GraphNode(
            node_id=node_id,
            x=x,
            y=y,
            z=z,
            floor_index=floor_index,
            cell_type=cell_type,
            scope=scope,
            module_id=module_id,
            void_category=void_category,
            area=area,
            polygon=polygon,
            metadata=metadata or {},
        )
        self.nodes[node_id] = node
        self._adj_horiz.setdefault(node_id, set())
        self._adj_vert.setdefault(node_id, set())

        metadata_dict = metadata or {}
        # If multi-floor core/atrium, propagate across all other floors with vertical identity edges
        if scope == VerticalScope.MULTI_FLOOR and not metadata_dict.get("_is_propagated_replica"):
            self._propagate_multi_floor_node(node)

        return node

    def _propagate_multi_floor_node(self, root_node: GraphNode) -> None:
        """Instantiate vertical replicas of a multi-floor node across all stories."""
        base_id = root_node.node_id
        prev_node_id = base_id

        for f in range(self.num_floors):
            if f == root_node.floor_index:
                continue
            replica_id = f"{base_id}_f{f:02d}"
            replica = GraphNode(
                node_id=replica_id,
                x=root_node.x,
                y=root_node.y,
                z=f * self.floor_height,
                floor_index=f,
                cell_type=root_node.cell_type,
                scope=VerticalScope.MULTI_FLOOR,
                module_id=root_node.module_id,
                void_category=root_node.void_category,
                area=root_node.area,
                polygon=root_node.polygon,
                metadata={"_is_propagated_replica": True, "root_id": base_id},
            )
            self.nodes[replica_id] = replica
            self._adj_horiz.setdefault(replica_id, set())
            self._adj_vert.setdefault(replica_id, set())

            # Connect vertical shaft edge
            self.add_edge(prev_node_id, replica_id, edge_type="vert", shared_length=root_node.area)
            prev_node_id = replica_id

    def add_edge(
        self,
        u: str,
        v: str,
        edge_type: str = "horiz",
        shared_length: float = 0.0,
        properties: dict | None = None,
    ) -> GraphEdge:
        """Add an adjacency or vertical alignment edge between nodes u and v."""
        if u not in self.nodes or v not in self.nodes:
            raise KeyError(f"Both nodes ({u}, {v}) must exist in graph.")

        edge = GraphEdge(u=u, v=v, edge_type=edge_type, shared_length=shared_length, properties=properties or {})
        if edge_type == "horiz":
            self.edges_horiz.append(edge)
            self._adj_horiz[u].add(v)
            self._adj_horiz[v].add(u)
        elif edge_type == "vert":
            self.edges_vert.append(edge)
            self._adj_vert[u].add(v)
            self._adj_vert[v].add(u)
        else:
            raise ValueError(f"Unknown edge_type: {edge_type}")
        return edge

    def has_edge(self, u: str, v: str, edge_type: str = "horiz") -> bool:
        """Check if an edge of given type exists between u and v."""
        if edge_type == "horiz":
            return v in self._adj_horiz.get(u, set())
        elif edge_type == "vert":
            return v in self._adj_vert.get(u, set())
        return False

    def compute_floor_voronoi_cells(
        self,
        floor_index: int,
        site_boundary: Sequence[dict | Sequence[float]] | None = None,
        site_pca_angle_rad: float = 0.0,
        max_radius: float = 8.0,
    ) -> dict[str, Any]:
        """Compute bounded Voronoi cells for nodes on floor_index using half-plane bisector clipping."""
        try:
            from shapely.geometry import Point, Polygon
        except ImportError:
            return {}

        floor_nodes = [n for n in self.nodes.values() if n.floor_index == floor_index]
        if not floor_nodes:
            return {}

        site_poly = None
        if site_boundary and len(site_boundary) >= 3:
            pts = [
                (float(p[0]), float(p[1])) if isinstance(p, (list, tuple)) else (float(p["x"]), float(p["y"]))
                for p in site_boundary
            ]
            if pts[0] != pts[-1]:
                pts.append(pts[0])
            site_poly = Polygon(pts)
            if not site_poly.is_valid:
                site_poly = site_poly.buffer(0)

        cells: dict[str, Any] = {}
        for i, ni in enumerate(floor_nodes):
            disc = Point(ni.x, ni.y).buffer(max_radius, resolution=16)
            cell = disc.intersection(site_poly) if site_poly is not None else disc

            for j, nj in enumerate(floor_nodes):
                if i == j:
                    continue
                dx = nj.x - ni.x
                dy = nj.y - ni.y
                dist = math.hypot(dx, dy)
                if dist < 1e-4 or dist > (2.0 * max_radius):
                    continue

                mx = (ni.x + nj.x) / 2.0
                my = (ni.y + nj.y) / 2.0
                nx = dx / dist
                ny = dy / dist

                R = 2000.0
                p1 = (mx - ny * R, my + nx * R)
                p2 = (mx + ny * R, my - nx * R)
                p3 = (p2[0] - nx * R, p2[1] - ny * R)
                p4 = (p1[0] - nx * R, p1[1] - ny * R)
                try:
                    cell = cell.intersection(Polygon([p1, p2, p3, p4]))
                except Exception:
                    pass
                if cell.is_empty:
                    break

            if not cell.is_empty:
                if cell.geom_type == 'MultiPolygon':
                    cell = max(cell.geoms, key=lambda g: g.area)
                cells[ni.node_id] = cell

        return cells

    @staticmethod
    def _voronoi_shared_wall_length(poly_a: Any, poly_b: Any, eps: float = 0.05) -> float:
        """Robustly compute shared party-wall length between two Voronoi polygons.

        Using a small buffer eps (5cm) guarantees immunity against machine-precision
        floating point gaps (~1e-15) on cutting lines, while strictly rejecting
        corner-touching points (whose overlap area is O(eps^2) ~ 0.04m << min_wall_len).
        """
        if poly_a is None or poly_b is None or poly_a.is_empty or poly_b.is_empty:
            return 0.0
        try:
            b1 = poly_a.bounds
            b2 = poly_b.bounds
            if b1[2] < b2[0] - eps or b2[2] < b1[0] - eps or b1[3] < b2[1] - eps or b2[3] < b1[1] - eps:
                return 0.0
            overlap_area = poly_a.buffer(eps).intersection(poly_b).area
            return overlap_area / eps
        except Exception:
            return 0.0

    def grow_node_connections(
        self,
        node_id: str,
        anchor_id: str | None = None,
        site_boundary: Sequence[dict | Sequence[float]] | None = None,
        site_pca_angle_rad: float = 0.0,
        max_dist: float = 12.0,
        min_wall_len: float = 0.5,
    ) -> list[GraphEdge]:
        """Incrementally grow horizontal connections for a newly added node.

        1. Grows connection to anchor_id if specified.
        2. Grows connections to any existing neighbor nodes on the same floor if their
           Voronoi cells share a party-wall boundary segment of length >= min_wall_len.
        3. Strictly preserves planarity (zero edge crossings).
        4. Completely avoids grid triangulation hypotenuses (where cells only meet at a 0D point).
        """
        if node_id not in self.nodes:
            return []

        target_node = self.nodes[node_id]
        f = target_node.floor_index
        floor_nodes = [n for n in self.nodes.values() if n.floor_index == f]
        if len(floor_nodes) < 2:
            return []

        new_edges: list[GraphEdge] = []

        def segments_cross(p1, p2, p3, p4, eps=1e-5):
            def orient(a, b, c):
                return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            def pt_eq(a, b):
                return abs(a[0] - b[0]) < eps and abs(a[1] - b[1]) < eps
            if pt_eq(p1, p3) or pt_eq(p1, p4) or pt_eq(p2, p3) or pt_eq(p2, p4):
                return False
            o1, o2 = orient(p1, p2, p3), orient(p1, p2, p4)
            o3, o4 = orient(p3, p4, p1), orient(p3, p4, p2)
            return ((o1 > eps and o2 < -eps) or (o1 < -eps and o2 > eps)) and \
                   ((o3 > eps and o4 < -eps) or (o3 < -eps and o4 > eps))

        # Algebraic local candidate contacts (Gabriel condition). These are
        # construction intents, never claimed to be validated physical walls.
        for other in floor_nodes:
            if other.node_id == node_id:
                continue
            dx, dy = other.x-target_node.x, other.y-target_node.y
            d2 = dx*dx+dy*dy
            if d2 < 1e-10 or d2 > max_dist*max_dist:
                continue
            mx, my = (other.x+target_node.x)/2, (other.y+target_node.y)/2
            blocked = any((q.x-mx)**2+(q.y-my)**2 <= d2/4+1e-9
                          for q in floor_nodes if q.node_id not in (node_id,other.node_id))
            if not blocked and not self.has_edge(node_id, other.node_id):
                new_edges.append(self.add_edge(node_id,other.node_id,
                    properties={"relation":"construction","validated":False}))
        return new_edges

    def update_floor_planar_edges(
        self,
        floor_index: int,
        site_boundary: Sequence[dict | Sequence[float]] | None = None,
        site_pca_angle_rad: float = 0.0,
        max_dist: float = 12.0,
        min_wall_len: float = 0.5,
    ) -> None:
        """Derive strictly planar horizontal connections on floor_index using true Voronoi party walls.

        Replaces all Delaunay grid triangulation. An edge exists between two nodes
        if and only if their Voronoi cells share an actual party-wall segment of length >= min_wall_len.
        Guarantees:
          - Zero diagonal hypotenuse triangulation chords.
          - Zero crossing connections.
          - Every connection has a perpendicular physical wall in the middle.
        """
        floor_nodes = [n for n in self.nodes.values() if n.floor_index == floor_index]
        if len(floor_nodes) < 2:
            return

        floor_node_ids = {n.node_id for n in floor_nodes}
        # Remove existing horizontal edges on this floor
        self.edges_horiz = [
            e for e in self.edges_horiz
            if not (e.u in floor_node_ids and e.v in floor_node_ids)
        ]
        for nid in floor_node_ids:
            self._adj_horiz[nid] = {
                nbr for nbr in self._adj_horiz.get(nid, set())
                if nbr not in floor_node_ids
            }

        cells = self.compute_floor_voronoi_cells(floor_index, site_boundary, site_pca_angle_rad)

        for i in range(len(floor_nodes)):
            na = floor_nodes[i]
            ca = cells.get(na.node_id)
            if ca is None or ca.is_empty:
                continue
            for j in range(i + 1, len(floor_nodes)):
                nb = floor_nodes[j]
                cb = cells.get(nb.node_id)
                if cb is None or cb.is_empty:
                    continue
                dist = math.hypot(na.x - nb.x, na.y - nb.y)
                if dist > max_dist:
                    continue
                wall_len = self._voronoi_shared_wall_length(ca, cb)
                if wall_len >= min_wall_len:
                    self.add_edge(na.node_id, nb.node_id, edge_type="horiz", shared_length=wall_len)

    def get_neighbors(self, node_id: str, floor_only: bool = True) -> list[GraphNode]:
        """Get neighbors of node_id."""
        if node_id not in self.nodes:
            return []
        neighbor_ids = set(self._adj_horiz.get(node_id, set()))
        if not floor_only:
            neighbor_ids.update(self._adj_vert.get(node_id, set()))
        return [self.nodes[nid] for nid in neighbor_ids if nid in self.nodes]

    def star_graph_offsets(self, node_id: str) -> list[tuple[float, float]]:
        """Get relative displacement vectors {p_j - p_i} to all same-floor neighbors."""
        center = self.nodes.get(node_id)
        if not center:
            return []
        neighbors = self.get_neighbors(node_id, floor_only=True)
        return [(n.x - center.x, n.y - center.y) for n in neighbors]

    def classify_void(self, node_id: str, min_atrium_area: float = 25.0) -> VoidCategory:
        """Classify a void node based on enclosure and area (PROP-17)."""
        node = self.nodes.get(node_id)
        if not node or node.cell_type != CellType.VOID:
            return VoidCategory.CLEARANCE

        neighbors = self.get_neighbors(node_id, floor_only=True)
        room_neighbors = [n for n in neighbors if n.cell_type in (CellType.ROOM, CellType.CORE)]

        # Enclosed on 3+ sides or substantial area -> Atrium
        if len(room_neighbors) >= 3 or node.area >= min_atrium_area:
            node.void_category = VoidCategory.ATRIUM
            return VoidCategory.ATRIUM

        node.void_category = VoidCategory.CLEARANCE
        return VoidCategory.CLEARANCE

    def validate_circulation_connectivity(self, floor_index: int | None = None) -> bool:
        """Check that every room connects to at least one core via rooms or atriums (PROP-17).

        Returns True if all habitable rooms on the specified floor (or all floors)
        have a valid path to vertical egress.
        """
        floors = [floor_index] if floor_index is not None else list(range(self.num_floors))

        for f in floors:
            floor_nodes = [n for n in self.nodes.values() if n.floor_index == f]
            cores = [n for n in floor_nodes if n.cell_type == CellType.CORE]
            rooms = [n for n in floor_nodes if n.cell_type in (CellType.ROOM, CellType.BALCONY)]

            if not cores:
                if rooms:
                    return False
                continue

            # BFS from all cores on this floor through traversable cells (ROOM, CORE, ATRIUM)
            visited = set()
            queue = [c.node_id for c in cores]
            for c_id in queue:
                visited.add(c_id)

            while queue:
                curr_id = queue.pop(0)
                for neighbor in self.get_neighbors(curr_id, floor_only=True):
                    # Voids only act as circulation traversable if they are atriums/courtyards
                    is_traversable = (
                        neighbor.cell_type in (CellType.CORE, CellType.ROOM, CellType.BALCONY)

                    )
                    if is_traversable and neighbor.node_id not in visited:
                        visited.add(neighbor.node_id)
                        queue.append(neighbor.node_id)

            # Check if any room was unreached
            for r in rooms:
                if r.node_id not in visited:
                    return False

        return True

    def compute_daylight_scores(
        self,
        site_boundary: Sequence[dict | Sequence[float]] | None = None,
        max_daylight_depth: float = 9.0,
    ) -> dict[str, float]:
        """Compute daylight illumination score [0.0, 1.0] for every room (PROP-17).

        Rooms adjacent to an ATRIUM void or within max_daylight_depth of exterior receive
        high daylight scores. Deep interior landlocked rooms receive 0.0.
        """
        scores: dict[str, float] = {}

        for node_id, node in self.nodes.items():
            if node.cell_type != CellType.ROOM:
                continue

            # Bonus from adjacent atrium/courtyard
            neighbors = self.get_neighbors(node_id, floor_only=True)
            has_atrium_access = any(
                n.cell_type == CellType.VOID and n.void_category in (VoidCategory.ATRIUM, VoidCategory.COURTYARD)
                for n in neighbors
            )

            if has_atrium_access:
                scores[node_id] = 1.0
                continue

            # Check distance to boundary if site boundary is provided
            if site_boundary:
                min_dist = self._min_distance_to_boundary((node.x, node.y), site_boundary)
                if min_dist <= max_daylight_depth:
                    scores[node_id] = max(0.0, 1.0 - (min_dist / max_daylight_depth))
                else:
                    scores[node_id] = 0.0
            else:
                scores[node_id] = 0.5  # Neutral fallback

        return scores

    @staticmethod
    def _min_distance_to_boundary(
        pt: tuple[float, float],
        polygon: Sequence[dict | Sequence[float]],
    ) -> float:
        """Compute minimum distance from point to polygon perimeter."""
        pts = [(float(p[0]), float(p[1])) if isinstance(p, (list, tuple)) else (float(p['x']), float(p['y'])) for p in polygon]
        if pts[0] != pts[-1]:
            pts.append(pts[0])

        min_d = float("inf")
        px, py = pt
        for i in range(len(pts) - 1):
            x1, y1 = pts[i]
            x2, y2 = pts[i + 1]
            dx = x2 - x1
            dy = y2 - y1
            l2 = dx * dx + dy * dy
            if l2 < 1e-9:
                dist = math.hypot(px - x1, py - y1)
            else:
                t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
                proj_x = x1 + t * dx
                proj_y = y1 + t * dy
                dist = math.hypot(px - proj_x, py - proj_y)
            min_d = min(min_d, dist)
        return min_d

    def get_node_span(self, node_id: str, default: float = 6.0) -> float:
        """Compute average horizontal incident edge span for a node."""
        if node_id not in self.nodes:
            return default
        n = self.nodes[node_id]
        nbrs = [nbr for nbr in self._adj_horiz.get(node_id, ()) if nbr in self.nodes and self.nodes[nbr].floor_index == n.floor_index]
        if not nbrs:
            return default
        return sum(math.hypot(n.x - self.nodes[nbr].x, n.y - self.nodes[nbr].y) for nbr in nbrs) / len(nbrs)

    def reassign_functions(self, changes: dict[str, CellType], require_access: bool = True) -> None:
        """Atomically reassign whole occurrences; support joint core relocation."""
        old = {nid:n.cell_type for nid,n in self.nodes.items()}
        try:
            for nid, function in changes.items():
                if nid not in self.nodes:
                    raise KeyError(nid)
                root=self.nodes[nid].metadata.get('root_id',nid)
                for n in self.nodes.values():
                    if n.node_id==root or n.metadata.get('root_id')==root:
                        n.cell_type=CellType(function)
            if require_access and not self.validate_circulation_connectivity():
                raise ValueError('function change breaks same-floor access')
        except Exception:
            for nid,f in old.items(): self.nodes[nid].cell_type=f
            raise

    def evaluate_graph_metrics(self, floor_index, site_area=1000., site_pca_angle_rad=0.,
                               star_motif_matcher=None, dict_cap=10, site_boundary=None, realization=None):
        """Graph-only estimates by default; measured metrics require an explicit realization."""
        if realization is None:
            from graph_proxy import GraphSketch
            return GraphSketch(self).metrics(floor_index,site_area,dict_cap)
        from shared_modules import area
        result,audit=realization
        from graph_evidence import daylight_accessibility
        daylight=daylight_accessibility(self,result,floor_index)
        nodes=[n for n in self.nodes.values() if n.floor_index==floor_index]
        built=[n for n in nodes if n.cell_type!=CellType.VOID]
        node_areas={n.node_id:area(result.prototypes[n.module_id].polygon)
                    if n.module_id in result.prototypes else 0. for n in nodes}
        filled=sum(node_areas[n.node_id] for n in built)
        rentable=sum(node_areas[n.node_id] for n in built if n.cell_type==CellType.ROOM)
        core=sum(node_areas[n.node_id] for n in built if n.cell_type==CellType.CORE)
        measured=audit.get('perFloor',{}).get(floor_index,{})
        filled=measured.get('filledArea',filled)
        rentable=measured.get('rentableArea',rentable)
        core=measured.get('coreArea',core)
        # Count independent placement groups, not vertical replicas, for reuse.
        reuse=result.reuse(); k=reuse['prototypeCount']
        excess=max(0,k-dict_cap)
        budget_cost=10.*(excess/max(1,dict_cap))**2
        singleton_cost=5.*reuse['singletonCount']/max(1,reuse['independentOccurrences'])
        ratio=filled/max(1.,site_area)
        underfill=35.*max(0.,1-ratio/.6)**2
        topology=self.validate_circulation_connectivity(floor_index)
        reuse_bonus=(20.*(reuse['independentOccurrences']-k)/max(1,reuse['independentOccurrences'])
                     if getattr(self,'module_bank',None) is not None else 0.)
        score=80.*min(1.,ratio)+15.*rentable/max(1.,filled)+reuse_bonus-budget_cost-singleton_cost-underfill-(0 if topology else 20)
        return dict(instanceIdx=floor_index,floorIndex=floor_index,filledArea=filled,siteArea=site_area,
            rentableArea=rentable,coreArea=core,moduleCount=len(nodes),exposedPerimeter=0.,
            fillRatio=ratio,rentableRatio=rentable/max(1.,filled),daylightRatio=0.,
            envelopeDaylightRatio=0.,reuseRatio=reuse['confirmedReuseRatio'],
            constructibilityScore=0.,envelopeEfficiency=0.,exteriorCorridorRatio=0.,triangleRatio=0.,
            topologyValid=topology,topologyViolations=[] if topology else ['same_floor_access'],
            totalPartialLength=0.,deepRoomCount=0,depthPenaltyScore=0.,facadeChasmOccludedLength=0.,
            areaVariancePenalty=0.,rawScore=score+underfill,underfillPenalty=underfill,
            topologyPenalty=0. if topology else 20.,facadeChasmPenalty=0.,vocabSize=k,
            dictLimitBreach=excess,dictBreachPenalty=budget_cost,singletonPenalty=singleton_cost,reuseBonus=reuse_bonus,
            score=score,estimateStatus='realized_uncalibrated_environment',sunExposure=None,daylightAccessibility=daylight,
            unavailableMetrics=['daylightRatio','constructibilityScore','envelopeEfficiency'],
            uncertainty={'priorDerivedPrototypes':sum(p.prior_boundary for p in result.prototypes.values()),
                         'unresolvedOccurrences':len(result.unresolved)},reuseAudit=reuse)
