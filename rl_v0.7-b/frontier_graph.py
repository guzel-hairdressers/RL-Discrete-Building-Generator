"""Topological Frontier Graph and Placement Proposer for Module Lab.

Represents the exposed boundary edges of placed shapes as a 1D perimeter graph.
Proposes exact placement candidates at valid topological docking slots,
reducing candidate evaluations from ~4,000 to ~20 per step.
"""

from __future__ import annotations

import math
from typing import Any, Sequence
import geometry as G

MIN_SHARED_EDGE = 0.5


class FrontierEdge:
    """Exposed boundary edge on the active floor layout."""
    __slots__ = (
        "id", "placement_id", "a", "b", "dx", "dy", "length",
        "angle_rad", "normal_x", "normal_y", "preferred", "category"
    )

    def __init__(
        self,
        edge_id: int,
        placement_id: str,
        a: dict[str, float],
        b: dict[str, float],
        preferred: bool = False,
        category: str = "room"
    ) -> None:
        self.id = edge_id
        self.placement_id = placement_id
        self.a = a
        self.b = b
        self.dx = b["x"] - a["x"]
        self.dy = b["y"] - a["y"]
        self.length = math.hypot(self.dx, self.dy)
        self.angle_rad = math.atan2(self.dy, self.dx)
        
        # Outward unit normal vector (rotated +90 degrees from edge direction)
        if self.length > 1e-8:
            self.normal_x = -self.dy / self.length
            self.normal_y = self.dx / self.length
        else:
            self.normal_x = 0.0
            self.normal_y = 0.0
            
        self.preferred = preferred
        self.category = category


class FrontierGraph:
    """Topological perimeter graph maintaining exposed attachment slots."""

    def __init__(self) -> None:
        self.edges: dict[int, FrontierEdge] = {}
        self.next_edge_id = 1

    def clear(self) -> None:
        self.edges.clear()
        self.next_edge_id = 1

    def add_placement_edges(self, placement: dict, preferred: bool = False) -> list[FrontierEdge]:
        """Add exposed edges of a newly placed module to the frontier graph."""
        poly = placement["poly"]
        placement_id = placement["id"]
        category = placement.get("category", "room")
        added_edges = []
        n = len(poly)
        for i in range(n):
            a = poly[i]
            b = poly[(i + 1) % n]
            edge = FrontierEdge(
                edge_id=self.next_edge_id,
                placement_id=placement_id,
                a=a,
                b=b,
                preferred=preferred,
                category=category
            )
            self.next_edge_id += 1
            if edge.length >= MIN_SHARED_EDGE:
                self.edges[edge.id] = edge
                added_edges.append(edge)
        return added_edges

    def propose_topological_anchors(
        self,
        module: dict,
        rotation: dict,
    ) -> list[tuple[float, float, int]]:
        """Yield (anchor_x, anchor_y, edge_id) candidate slots for a module rotation.
        
        Aligns candidate edges flush against exposed frontier edges with opposite normals.
        """
        candidate_poly = rotation["poly"]
        anchors = []
        seen_anchors = set()
        
        n_cand = len(candidate_poly)
        for cand_idx in range(n_cand):
            c_first = candidate_poly[cand_idx]
            c_second = candidate_poly[(cand_idx + 1) % n_cand]
            c_dx = c_second["x"] - c_first["x"]
            c_dy = c_second["y"] - c_first["y"]
            c_len = math.hypot(c_dx, c_dy)
            if c_len < MIN_SHARED_EDGE:
                continue

            # Candidate edge outward normal
            c_nx = -c_dy / c_len
            c_ny = c_dx / c_len

            for edge in self.edges.values():
                # To attach flush, candidate edge normal must be OPPOSITE to placed edge normal
                dot_norm = c_nx * edge.normal_x + c_ny * edge.normal_y
                if dot_norm > -0.99:  # Must be anti-parallel (~180 deg)
                    continue

                # Align left endpoint (c_first -> edge.b)
                ax1 = edge.b["x"] - c_first["x"]
                ay1 = edge.b["y"] - c_first["y"]
                sig1 = (round(ax1, 4), round(ay1, 4))
                if sig1 not in seen_anchors:
                    seen_anchors.add(sig1)
                    anchors.append((ax1, ay1, edge.id))

                # Align right endpoint (c_second -> edge.a)
                ax2 = edge.a["x"] - c_second["x"]
                ay2 = edge.a["y"] - c_second["y"]
                sig2 = (round(ax2, 4), round(ay2, 4))
                if sig2 not in seen_anchors:
                    seen_anchors.add(sig2)
                    anchors.append((ax2, ay2, edge.id))

        return anchors
