import os
import sys
import unittest

MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if MODULE_DIR not in sys.path:
    sys.path.insert(0, MODULE_DIR)

import geometry as G
import graph
import server


class V06DCustomTests(unittest.TestCase):
    def test_custom_polygon_synthesis_enforces_triangles_and_quads_only(self) -> None:
        # k=3 (triangle) succeeds
        poly3 = G.synthesize_custom_polygon(3, [3.0, 4.0], [60.0])
        self.assertEqual(len(poly3), 3)

        # k=4 (quad) succeeds
        poly4 = G.synthesize_custom_polygon(4, [3.0, 4.0, 3.0], [90.0, 90.0])
        self.assertEqual(len(poly4), 4)

        # k=5 (5-gon) fails
        with self.assertRaises(ValueError):
            G.synthesize_custom_polygon(5, [3.0, 4.0, 3.0, 4.0], [90.0, 90.0, 90.0])

    def test_dictionary_limit_breach_squared_penalty(self) -> None:
        trainer = server.ParallelTrainer()
        trainer.settings["dictionarySizeLimit"] = 2
        
        # Add 4 dummy modules to preliminary dictionary to create a breach of 2
        for idx in range(4):
            trainer.dictionary.append(
                {
                    "id": f"s_test_{idx}",
                    "name": f"Test {idx}",
                    "category": "room",
                    "area": 9.0,
                    "poly": [{"x": 0.0, "y": 0.0}, {"x": 3.0, "y": 0.0}, {"x": 3.0, "y": 3.0}, {"x": 0.0, "y": 3.0}],
                }
            )

        event = trainer._finish_episode()
        metrics = event["metrics"]

        # Breach = 4 - 2 = 2. Penalty = 2^2 * 5.0 = 20.0
        self.assertEqual(metrics["dictLimitBreach"], 2)
        self.assertEqual(metrics["dictBreachPenalty"], 20.0)

    def test_custom_shape_sampling_respects_min_edge(self) -> None:
        trainer = server.ParallelTrainer()
        trainer.update_settings({"minEdge": 3.0, "maxEdge": 9.0})

        for idx in range(10):
            module, _ = trainer._sample_custom_shape(trainer.settings, trainer.environments, idx)
            lengths = G._edge_lengths(module["poly"])
            self.assertTrue(
                all(l >= 3.0 - 1e-4 for l in lengths),
                f"Generated module edges {lengths} contain length < minEdge (3.0m)"
            )


if __name__ == "__main__":
    unittest.main()
