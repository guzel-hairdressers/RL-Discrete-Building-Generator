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

    def test_parallel_trainer_graph_voronoi_step(self):
        from server import ParallelTrainer
        trainer = ParallelTrainer(settings={"generatorEngine": "graph_voronoi"})
        trainer.new_site()
        event = trainer.step(trainer.generation_id, trainer.episode)
        self.assertIn("graphState", event)
        self.assertGreater(len(event["graphState"]["nodes"]), 0)
        self.assertIn("world_x", event["graphState"]["nodes"][0])
        self.assertIn("edgesHoriz", event["graphState"])
        self.assertIn("edgesVert", event["graphState"])

    def test_parallel_trainer_graph_voronoi_full_episode(self):
        from server import ParallelTrainer
        trainer = ParallelTrainer(settings={"generatorEngine": "graph_voronoi"})
        trainer.new_site()
        event = None
        for _ in range(35):
            event = trainer.step(trainer.generation_id, trainer.episode)
            if event.get("type") == "episodeDone":
                break
        self.assertIsNotNone(event)
        self.assertEqual(event.get("type"), "episodeDone")
        self.assertIn("placements", event)
        self.assertGreater(len(event["placements"]), 0)

    def test_strictly_planar_horizontal_edges_no_crossings(self):
        """Verify that horizontal floor graph edges are strictly planar with 0 crossings."""
        graph = BuildingGraph(num_floors=1)
        nodes = []
        # Add 3x3 grid of nodes
        for row in range(3):
            for col in range(3):
                nid = f"n_{row}_{col}"
                graph.add_node(nid, col * 6.0, row * 6.0, floor_index=0)
                nodes.append(nid)

        # Enforce planar Voronoi party-wall topology (no grid triangulation)
        graph.update_floor_planar_edges(0, max_dist=10.0)
        edges = graph.edges_horiz
        # In a 3x3 square grid, there are exactly 12 orthogonal party walls and 0 diagonal hypotenuses
        self.assertEqual(len(edges), 12, f"Expected 12 orthogonal edges, got {len(edges)}")

        # Verify no diagonal hypotenuses exist (orthogonal grid has only pure horizontal or vertical edges)
        for e in edges:
            n1, n2 = graph.nodes[e.u], graph.nodes[e.v]
            dx = abs(n1.x - n2.x)
            dy = abs(n1.y - n2.y)
            self.assertTrue(
                (dx < 1e-4 and abs(dy - 6.0) < 1e-4) or (dy < 1e-4 and abs(dx - 6.0) < 1e-4),
                f"Edge {e.u}-{e.v} is a diagonal hypotenuse! dx={dx}, dy={dy}",
            )

        # Check all pairs of segments for internal intersections (crossings)
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

        crossings = 0
        for i in range(len(edges)):
            for j in range(i + 1, len(edges)):
                e1, e2 = edges[i], edges[j]
                n1, n2 = graph.nodes[e1.u], graph.nodes[e1.v]
                n3, n4 = graph.nodes[e2.u], graph.nodes[e2.v]
                if segments_cross((n1.x, n1.y), (n2.x, n2.y), (n3.x, n3.y), (n4.x, n4.y)):
                    crossings += 1

        self.assertEqual(crossings, 0, f"Found {crossings} crossing edge connections!")

    def test_incremental_connection_growth(self):
        """Verify that connections grow incrementally step-by-step with 0 diagonal hypotenuses."""
        graph = BuildingGraph(num_floors=1)
        # Place central core
        graph.add_node("core", 6.0, 6.0, floor_index=0, cell_type=CellType.CORE)

        growth_steps = [
            ("n_top", 6.0, 12.0, "core"),
            ("n_bot", 6.0, 0.0, "core"),
            ("n_left", 0.0, 6.0, "core"),
            ("n_right", 12.0, 6.0, "core"),
            ("n_tl", 0.0, 12.0, "n_top"),
            ("n_tr", 12.0, 12.0, "n_top"),
            ("n_bl", 0.0, 0.0, "n_bot"),
            ("n_br", 12.0, 0.0, "n_bot"),
        ]

        for nid, x, y, anchor_id in growth_steps:
            graph.add_node(nid, x, y, floor_index=0, cell_type=CellType.ROOM)
            new_edges = graph.grow_node_connections(node_id=nid, anchor_id=anchor_id, max_dist=10.0)
            self.assertGreater(len(new_edges), 0, f"No edges grew when placing {nid} from {anchor_id}")

        # Final 3x3 layout must have exactly 12 orthogonal edges
        self.assertEqual(len(graph.edges_horiz), 12)
        for e in graph.edges_horiz:
            n1, n2 = graph.nodes[e.u], graph.nodes[e.v]
            dx = abs(n1.x - n2.x)
            dy = abs(n1.y - n2.y)
            self.assertTrue(
                (dx < 1e-4 and abs(dy - 6.0) < 1e-4) or (dy < 1e-4 and abs(dx - 6.0) < 1e-4),
                f"Incremental growth formed diagonal hypotenuse {e.u}-{e.v}! dx={dx}, dy={dy}",
            )

    def test_module_area_capping_and_no_boundary_stretch(self):
        """Verify that room modules are strictly capped (<= 50m2) and do not stretch to distant boundaries."""
        graph = BuildingGraph(num_floors=1)
        # Giant 200x200m site
        giant_site = [(0.0, 0.0), (200.0, 0.0), (200.0, 200.0), (0.0, 200.0)]
        graph.add_node("center_core", 100.0, 100.0, cell_type=CellType.CORE, floor_index=0)
        graph.add_node("r1", 106.0, 100.0, cell_type=CellType.ROOM, floor_index=0)

        rooms = self.realizer.realize_floor(graph=graph, floor_index=0, site_boundary=giant_site)
        self.assertEqual(len(rooms), 2)
        for r in rooms:
            self.assertLessEqual(r["area"], 50.0, f"Room {r['node_id']} exceeded 50m2: {r['area']}")
            # Ensure room vertices did not stretch all the way to 0 or 200
            for px, py in r["polygon"]:
                self.assertGreater(px, 50.0)
                self.assertLess(px, 150.0)
                self.assertGreater(py, 50.0)
                self.assertLess(py, 150.0)

    def test_repeatable_modules_congruence_grouping(self):
        """Verify that congruent grid modules share the identical moduleId and have use counts >= 2."""
        graph = BuildingGraph(num_floors=1)
        site = [(0.0, 0.0), (60.0, 0.0), (60.0, 60.0), (0.0, 60.0)]
        # Add 4 congruent rooms on a 6m grid
        for i, (x, y) in enumerate([(20.0, 20.0), (26.0, 20.0), (20.0, 26.0), (26.0, 26.0)]):
            graph.add_node(f"room_{i}", x, y, cell_type=CellType.ROOM, floor_index=0)

        rooms = self.realizer.realize_floor(graph=graph, floor_index=0, site_boundary=site)
        self.assertEqual(len(rooms), 4)
        module_ids = [r["module_id"] for r in rooms]
        # At least some rooms should share the exact same template
        from collections import Counter
        counts = Counter(module_ids)
        self.assertTrue(any(c >= 2 for c in counts.values()), f"Expected repeatable modules, got: {counts}")

    def test_evaluate_on_pause_returns_canonical_dictionary(self):
        """Verify that evaluate (called on Pause) populates dictionary with repeated modules."""
        from server import ParallelTrainer
        trainer = ParallelTrainer(settings={"generatorEngine": "graph_voronoi"})
        trainer.new_site()
        for _ in range(5):
            trainer.step(trainer.generation_id, trainer.episode)

        eval_event = trainer.evaluate(trainer.generation_id, trainer.episode)
        self.assertIn("dictionary", eval_event)
        self.assertIn("placements", eval_event)
        self.assertGreater(len(eval_event["placements"]), 0)
        self.assertGreater(len(eval_event["dictionary"]), 0)
        # Check that modules have area and uses
        first_mod = eval_event["dictionary"][0]
        self.assertIn("area", first_mod)
        self.assertIn("uses", first_mod)
        self.assertGreaterEqual(first_mod["uses"], 1)


if __name__ == "__main__":
    unittest.main()

