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
                        or (neighbor.cell_type == CellType.VOID and neighbor.void_category == VoidCategory.ATRIUM)
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
