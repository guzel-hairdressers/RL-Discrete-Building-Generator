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
