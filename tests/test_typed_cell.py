"""Unit tests for PROP-17 Typed-Cell Ontology & Hierarchical BuildingGraph."""

import unittest

from typed_cell import (
    BuildingGraph,
    CellType,
    VerticalScope,
    VoidCategory,
)


class TestTypedCell(unittest.TestCase):
    """Test multi-floor graph construction, typed cells, and connectivity invariants."""

    def test_multi_floor_core_propagation(self):
        graph = BuildingGraph(num_floors=4, floor_height=3.5)
        core = graph.add_node(
            node_id="core_01",
            x=10.0,
            y=10.0,
            floor_index=0,
            cell_type=CellType.CORE,
            scope=VerticalScope.MULTI_FLOOR,
            area=36.0,
        )

        # Core should exist on floor 0 and have replicas on floors 1, 2, 3
        self.assertEqual(len(graph.nodes), 4)
        for f in range(4):
            expected_id = "core_01" if f == 0 else f"core_01_f{f:02d}"
            self.assertIn(expected_id, graph.nodes)
            node = graph.nodes[expected_id]
            self.assertEqual(node.floor_index, f)
            self.assertEqual(node.z, f * 3.5)
            self.assertEqual(node.cell_type, CellType.CORE)
            self.assertEqual(node.scope, VerticalScope.MULTI_FLOOR)

        # Should have vertical coupling edges connecting the shaft
        self.assertGreaterEqual(len(graph.edges_vert), 3)

    def test_horizontal_adjacencies_and_star_graph(self):
        graph = BuildingGraph(num_floors=2)
        c = graph.add_node("c", 0.0, 0.0, floor_index=0)
        n1 = graph.add_node("n1", 5.0, 0.0, floor_index=0)
        n2 = graph.add_node("n2", 0.0, 5.0, floor_index=0)
        n3 = graph.add_node("n3", -5.0, 0.0, floor_index=0)

        graph.add_edge("c", "n1")
        graph.add_edge("c", "n2")
        graph.add_edge("c", "n3")

        neighbors = graph.get_neighbors("c", floor_only=True)
        self.assertEqual(len(neighbors), 3)

        offsets = set(graph.star_graph_offsets("c"))
        expected_offsets = {(5.0, 0.0), (0.0, 5.0), (-5.0, 0.0)}
        self.assertEqual(offsets, expected_offsets)

    def test_void_classification(self):
        graph = BuildingGraph(num_floors=1)
        # Atrium: enclosed by 3 rooms
        v1 = graph.add_node("v1", 0.0, 0.0, cell_type=CellType.VOID, area=30.0)
        r1 = graph.add_node("r1", 5.0, 0.0, cell_type=CellType.ROOM)
        r2 = graph.add_node("r2", -5.0, 0.0, cell_type=CellType.ROOM)
        r3 = graph.add_node("r3", 0.0, 5.0, cell_type=CellType.ROOM)
        graph.add_edge("v1", "r1")
        graph.add_edge("v1", "r2")
        graph.add_edge("v1", "r3")

        cat1 = graph.classify_void("v1")
        self.assertEqual(cat1, VoidCategory.ATRIUM)

        # Clearance: small narrow ditch with only 1 room neighbor
        v2 = graph.add_node("v2", 20.0, 20.0, cell_type=CellType.VOID, area=4.0)
        r4 = graph.add_node("r4", 22.0, 20.0, cell_type=CellType.ROOM)
        graph.add_edge("v2", "r4")
        cat2 = graph.classify_void("v2")
        self.assertEqual(cat2, VoidCategory.CLEARANCE)

    def test_circulation_connectivity_validation(self):
        graph = BuildingGraph(num_floors=1)
        # Core connected to room1, room1 connected to room2
        graph.add_node("core", 0.0, 0.0, cell_type=CellType.CORE)
        graph.add_node("r1", 5.0, 0.0, cell_type=CellType.ROOM)
        graph.add_node("r2", 10.0, 0.0, cell_type=CellType.ROOM)
        graph.add_edge("core", "r1")
        graph.add_edge("r1", "r2")

        self.assertTrue(graph.validate_circulation_connectivity())

        # Add isolated detached room without path to core
        graph.add_node("isolated_r", 50.0, 50.0, cell_type=CellType.ROOM)
        self.assertFalse(graph.validate_circulation_connectivity())

    def test_daylight_scoring_with_atrium_and_boundary(self):
        graph = BuildingGraph(num_floors=1)
        # Room adjacent to atrium gets 1.0
        graph.add_node("atrium", 0.0, 0.0, cell_type=CellType.VOID)
        r_atrium = graph.add_node("r_atrium", 3.0, 0.0, cell_type=CellType.ROOM)
        graph.add_edge("atrium", "r_atrium")
        graph.classify_void("atrium", min_atrium_area=0.0) # force atrium

        # Room close to boundary gets high score
        r_perimeter = graph.add_node("r_perimeter", 2.0, 2.0, cell_type=CellType.ROOM)
        # Room far from boundary gets 0.0
        r_deep = graph.add_node("r_deep", 20.0, 20.0, cell_type=CellType.ROOM)

        boundary = [(0.0, 0.0), (30.0, 0.0), (30.0, 30.0), (0.0, 30.0)]
        scores = graph.compute_daylight_scores(site_boundary=boundary, max_daylight_depth=9.0)

        self.assertEqual(scores["r_atrium"], 1.0)
        self.assertGreater(scores["r_perimeter"], 0.7)
        self.assertEqual(scores["r_deep"], 0.0)


if __name__ == "__main__":
    unittest.main()
