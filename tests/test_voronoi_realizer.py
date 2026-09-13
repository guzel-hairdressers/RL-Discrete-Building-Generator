"""Unit tests for PROP-16 C SE(2) Motif Matcher & Voronoi Realizer."""

import math
import unittest

from typed_cell import BuildingGraph, CellType
from voronoi_realizer import SE2MotifMatcher, VoronoiRealizer


class TestVoronoiRealizer(unittest.TestCase):
    """Test arbitrary-angle SE(2) congruence and Voronoi template dictation."""

    def setUp(self):
        self.matcher = SE2MotifMatcher(tolerance=0.15)
        self.realizer = VoronoiRealizer(matcher=self.matcher)

    def test_se2_congruence_under_arbitrary_rotation(self):
        # Base star: cross with arms of lengths 4.0, 5.0, 6.0, 7.0
        base_star = [(4.0, 0.0), (0.0, 5.0), (-6.0, 0.0), (0.0, -7.0)]

        # Rotate by arbitrary continuous angle (e.g. 37.5 degrees)
        theta_deg = 37.5
        theta = math.radians(theta_deg)
        c, s = math.cos(theta), math.sin(theta)
        rotated_star = [(x * c - y * s, x * s + y * c) for x, y in base_star]

        is_cong, phi = self.matcher.are_stars_congruent(base_star, rotated_star)
        self.assertTrue(is_cong)
        # Verify detected rotation matches 37.5 degrees
        detected_deg = (math.degrees(phi) + 360.0) % 360.0
        self.assertAlmostEqual(detected_deg, theta_deg, places=2)

    def test_se2_rejection_of_different_angles(self):
        # Star A: 90-degree internal angle
        star_a = [(5.0, 0.0), (0.0, 5.0)]
        # Star B: 60-degree internal angle
        star_b = [(5.0, 0.0), (2.5, 4.33)]

        is_cong, _ = self.matcher.are_stars_congruent(star_a, star_b)
        self.assertFalse(is_cong)

    def test_submotif_perimeter_to_master_dictation(self):
        # Master star with 4 neighbors (fully enclosed interior room)
        master_star = [(5.0, 0.0), (0.0, 5.0), (-5.0, 0.0), (0.0, -5.0)]

        # Perimeter node has only 2 interior neighbors at 90 degrees
        perimeter_star = [(5.0, 0.0), (0.0, 5.0)]

        # Perimeter star should be recognized as a submotif of master
        is_sub, _ = self.matcher.is_submotif(perimeter_star, master_star)
        self.assertTrue(is_sub)

        # Perimeter star rotated by 45 degrees should ALSO be recognized as a submotif
        theta = math.radians(45.0)
        c, s = math.cos(theta), math.sin(theta)
        rot_perimeter = [(x * c - y * s, x * s + y * c) for x, y in perimeter_star]

        is_sub_rot, phi = self.matcher.is_submotif(rot_perimeter, master_star)
        self.assertTrue(is_sub_rot)
        self.assertAlmostEqual(abs(math.degrees(phi)), 45.0, delta=1.0)

    def test_voronoi_floor_realization_and_template_dictation(self):
        site_boundary = [(0.0, 0.0), (40.0, 0.0), (40.0, 40.0), (0.0, 40.0)]
        graph = BuildingGraph(num_floors=1)

        # Master interior node with 4 neighbors
        m = graph.add_node("master", 20.0, 20.0, cell_type=CellType.ROOM)
        n1 = graph.add_node("n1", 28.0, 20.0, cell_type=CellType.ROOM)
        n2 = graph.add_node("n2", 20.0, 28.0, cell_type=CellType.ROOM)
        n3 = graph.add_node("n3", 12.0, 20.0, cell_type=CellType.ROOM)
        n4 = graph.add_node("n4", 20.0, 12.0, cell_type=CellType.ROOM)

        graph.add_edge("master", "n1")
        graph.add_edge("master", "n2")
        graph.add_edge("master", "n3")
        graph.add_edge("master", "n4")

        # n1 is on the perimeter with fewer neighbors: connects to master and n2
        graph.add_edge("n1", "n2")

        rooms = self.realizer.realize_floor(
            graph=graph,
            floor_index=0,
            site_boundary=site_boundary,
        )

        self.assertGreaterEqual(len(rooms), 1)

        # Master room should be identified as a master template
        master_room = [r for r in rooms if r["node_id"] == "master"][0]
        self.assertTrue(master_room["is_master_template"])
        self.assertGreater(master_room["area"], 10.0)

        # Cells must be valid polygons inside the boundary
        for r in rooms:
            self.assertIsNotNone(r["polygon"])
            self.assertGreaterEqual(len(r["polygon"]), 3)

    def test_floor_environment_voronoi_realization(self):
        from server import FloorEnvironment
        import geometry as G

        boundary = {
            "polygon": [{"x": 0.0, "y": 0.0}, {"x": 40.0, "y": 0.0}, {"x": 40.0, "y": 40.0}, {"x": 0.0, "y": 40.0}],
            "area": 1600.0,
        }
        env = FloorEnvironment(
            index=0,
            boundary=boundary,
            atrium_choice={"type": "none"},
            site={"area": 1600.0},
            offset=(0.0, 0.0),
            rng=G.RNG(42),
        )

        # Add nodes to the floor's building graph
        env.building_graph.add_node("c0", 20.0, 20.0, cell_type=CellType.CORE)
        env.building_graph.add_node("r1", 28.0, 20.0, cell_type=CellType.ROOM)
        env.building_graph.add_node("r2", 20.0, 28.0, cell_type=CellType.ROOM)
        env.building_graph.add_edge("c0", "r1")
        env.building_graph.add_edge("c0", "r2")

        placements = env.realize_graph_voronoi_placements()
        self.assertEqual(len(placements), 3)
        self.assertTrue(any(p["category"] == "core" for p in placements))
        self.assertTrue(all(len(p["poly"]) >= 3 for p in placements))


if __name__ == "__main__":
    unittest.main()

