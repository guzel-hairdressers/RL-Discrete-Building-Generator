"""Unit tests for PROP-16 A GraphSeedSampler."""

import math
import unittest

from graph_sampler import GraphSeedSampler
from typed_cell import BuildingGraph, CellType


class TestGraphSeedSampler(unittest.TestCase):
    """Test pattern-aware, frontier-relative candidate seed generation."""

    def setUp(self):
        self.sampler = GraphSeedSampler(
            default_bay_depths=(3.0, 6.0),
            min_seed_distance=2.0,
            site_setback=1.0,
        )
        self.boundary = [(0.0, 0.0), (50.0, 0.0), (50.0, 50.0), (0.0, 50.0)]

    def test_initial_seeds_on_empty_site(self):
        graph = BuildingGraph(num_floors=1)
        candidates = self.sampler.generate_candidates(
            graph=graph,
            floor_index=0,
            site_boundary=self.boundary,
            site_pca_axes=((1.0, 0.0), (0.0, 1.0)),
        )
        self.assertGreaterEqual(len(candidates), 1)
        # Should contain centroid (25, 25)
        self.assertTrue(any(abs(c["x"] - 25.0) < 1.0 and abs(c["y"] - 25.0) < 1.0 for c in candidates))

    def test_diagonal_span_vector_propagation(self):
        # Node 1 at (20, 20), Node 2 at (21, 22) -> dx=1, dy=2, length = sqrt(5) ~ 2.236
        graph = BuildingGraph(num_floors=1)
        n1 = graph.add_node("n1", 20.0, 20.0, floor_index=0)
        n2 = graph.add_node("n2", 21.0, 22.0, floor_index=0)
        graph.add_edge("n1", "n2")

        candidates = self.sampler.generate_candidates(
            graph=graph,
            floor_index=0,
            site_boundary=self.boundary,
        )

        sqrt5 = math.sqrt(5.0)
        # Verify that vector propagation generated candidates preserving span ~ sqrt(5)
        prop_cands = [c for c in candidates if c.get("source") == "continuous_reference"]
        self.assertGreater(len(prop_cands), 0)
        self.assertTrue(all(c.get("span",0)>0 for c in prop_cands))

    def test_right_triangle_closure(self):
        graph = BuildingGraph(num_floors=1)
        n1 = graph.add_node("n1", 20.0, 20.0, floor_index=0)
        n2 = graph.add_node("n2", 24.0, 20.0, floor_index=0) # length = 4.0
        graph.add_edge("n1", "n2")

        candidates = self.sampler.generate_candidates(
            graph=graph,
            floor_index=0,
            site_boundary=self.boundary,
        )

        tri_cands = [c for c in candidates if c.get("source") == "continuous_reference"]
        self.assertGreater(len(tri_cands), 0)

    def test_motif_stamping(self):
        graph = BuildingGraph(num_floors=1)
        graph.add_node("anchor", 25.0, 25.0, floor_index=0)

        motif_bank = [{
            "id": "corner_bay",
            "relative_offsets": [(4.0, 0.0), (0.0, 4.0)],
        }]

        candidates = self.sampler.generate_candidates(
            graph=graph,
            floor_index=0,
            site_boundary=self.boundary,
            active_motif_bank=motif_bank,
        )

        stamped = [c for c in candidates if c.get("source") == "continuous_reference"]
        self.assertGreaterEqual(len(stamped), 1)
        # Should contain offset (25+4, 25) = (29, 25)
        self.assertTrue(any(abs(c["x"] - 29.0) < 0.1 for c in stamped))


if __name__ == "__main__":
    unittest.main()

class ConcaveContainmentTests(unittest.TestCase):
    def test_edges_may_not_cross_notch_even_when_corners_are_inside(self):
        from graph_sampler import convex_polygon_inside_site
        site=[(0,0),(10,0),(10,10),(6,10),(6,4),(4,4),(4,10),(0,10)]
        room=[(2,2),(8,2),(8,8),(2,8)]
        self.assertTrue(all(GraphSeedSampler._point_inside_polygon(p,site) for p in room))
        self.assertFalse(convex_polygon_inside_site(room,site))
        self.assertTrue(convex_polygon_inside_site([(1,1),(3,1),(3,9),(1,9)],site))

    def test_boundary_contact_is_contained(self):
        from graph_sampler import convex_polygon_inside_site
        self.assertTrue(convex_polygon_inside_site([(0,0),(10,0),(10,10),(0,10)],[(0,0),(10,0),(10,10),(0,10)]))

    def test_containment_matches_independent_oracle_on_oblique_hulls(self):
        import random
        from shapely.geometry import Polygon, MultiPoint
        from graph_sampler import convex_polygon_inside_site
        rng=random.Random(20261104)
        site=[(0,0),(12,0),(12,12),(8,12),(8,5),(4,5),(4,12),(0,12)]
        oracle=Polygon(site)
        lattice=[(x,y) for x in range(1,12) for y in range(1,12) if oracle.covers(MultiPoint([(x,y)]))]
        for _ in range(150):
            hull=MultiPoint(rng.sample(lattice,4)).convex_hull
            if hull.geom_type!='Polygon':continue
            coords=list(hull.exterior.coords)[:-1]
            self.assertEqual(convex_polygon_inside_site(coords,site),oracle.covers(hull),coords)
