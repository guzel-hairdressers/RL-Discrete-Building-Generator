"""Unit tests for FrontierGraph and topological anchor proposer."""

from __future__ import annotations

import unittest
import math
from frontier_graph import FrontierGraph, FrontierEdge


class TestFrontierGraph(unittest.TestCase):
    """Test suite for FrontierGraph functionality."""

    def setUp(self) -> None:
        self.graph = FrontierGraph()

    def test_add_placement_edges(self) -> None:
        placement = {
            "id": "P1",
            "category": "room",
            "poly": [
                {"x": 0.0, "y": 0.0},
                {"x": 4.0, "y": 0.0},
                {"x": 4.0, "y": 4.0},
                {"x": 0.0, "y": 4.0},
            ]
        }
        added = self.graph.add_placement_edges(placement)
        self.assertEqual(len(added), 4)
        self.assertEqual(len(self.graph.edges), 4)

    def test_propose_topological_anchors(self) -> None:
        placed = {
            "id": "P1",
            "category": "room",
            "poly": [
                {"x": 0.0, "y": 0.0},
                {"x": 4.0, "y": 0.0},
                {"x": 4.0, "y": 4.0},
                {"x": 0.0, "y": 4.0},
            ]
        }
        self.graph.add_placement_edges(placed)

        cand_module = {"id": "M_square", "category": "room"}
        cand_rotation = {
            "angle": 0.0,
            "poly": [
                {"x": 0.0, "y": 0.0},
                {"x": 4.0, "y": 0.0},
                {"x": 4.0, "y": 4.0},
                {"x": 0.0, "y": 4.0},
            ]
        }

        anchors = self.graph.propose_topological_anchors(cand_module, cand_rotation)
        self.assertTrue(len(anchors) > 0)


if __name__ == "__main__":
    unittest.main()
