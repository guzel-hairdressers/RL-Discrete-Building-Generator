"""Parity contracts for the standalone graph-frontier evaluation."""

from __future__ import annotations

import pathlib
import sys
import unittest


MODULE_DIR = pathlib.Path(__file__).resolve().parents[1]
BENCHMARK_DIR = MODULE_DIR / "benchmarks"
sys.path.insert(0, str(MODULE_DIR / "src"))
sys.path.insert(0, str(BENCHMARK_DIR))

import benchmark_graph_frontier as evaluation  # noqa: E402


class GraphFrontierEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.environment, _ = evaluation.make_grid_environment(12, 8)
        cls.module, cls.rotation = evaluation.square_probe()

    def test_unbounded_angle_index_is_lossless_against_residual_scan(self) -> None:
        indexed = evaluation.anchor_signatures(
            evaluation.exact_indexed_anchors(self.environment, self.rotation)
        )
        exhaustive = evaluation.anchor_signatures(
            evaluation.exhaustive_residual_anchors(self.environment, self.rotation)
        )
        self.assertEqual(indexed, exhaustive)

        indexed_legal = evaluation.legal_action_signatures(
            self.environment,
            self.module,
            self.rotation,
            evaluation.exact_indexed_anchors(self.environment, self.rotation),
        )
        exhaustive_legal = evaluation.legal_action_signatures(
            self.environment,
            self.module,
            self.rotation,
            evaluation.exhaustive_residual_anchors(self.environment, self.rotation),
        )
        self.assertEqual(indexed_legal, exhaustive_legal)

    def test_production_match_cap_is_intentionally_not_lossless(self) -> None:
        bounded = evaluation.anchor_signatures(
            evaluation.current_bounded_anchors(self.environment, self.rotation)
        )
        exact = evaluation.anchor_signatures(
            evaluation.exact_indexed_anchors(self.environment, self.rotation)
        )
        self.assertLess(len(bounded), len(exact))
        self.assertTrue(bounded < exact)

        bounded_legal = evaluation.legal_action_signatures(
            self.environment,
            self.module,
            self.rotation,
            evaluation.current_bounded_anchors(self.environment, self.rotation),
        )
        exact_legal = evaluation.legal_action_signatures(
            self.environment,
            self.module,
            self.rotation,
            evaluation.exact_indexed_anchors(self.environment, self.rotation),
        )
        self.assertLess(len(bounded_legal), len(exact_legal))
        self.assertTrue(bounded_legal < exact_legal)

    def test_recovered_raw_graph_keeps_spurious_internal_edge_proposals(self) -> None:
        raw = evaluation.anchor_signatures(
            evaluation.proposed_raw_graph_anchors(self.environment, self.rotation)
        )
        exact = evaluation.anchor_signatures(
            evaluation.exact_indexed_anchors(self.environment, self.rotation)
        )
        self.assertGreater(len(raw), len(exact))
        self.assertTrue(raw - exact)

        raw_legal = evaluation.legal_action_signatures(
            self.environment,
            self.module,
            self.rotation,
            evaluation.proposed_raw_graph_anchors(self.environment, self.rotation),
        )
        exact_legal = evaluation.legal_action_signatures(
            self.environment,
            self.module,
            self.rotation,
            evaluation.exact_indexed_anchors(self.environment, self.rotation),
        )
        self.assertEqual(raw_legal, exact_legal)


if __name__ == "__main__":
    unittest.main()
