"""Shared-policy trainer, topology, and transactional settings tests."""

from __future__ import annotations

import json
import os
import pathlib
import sys
import unittest
from unittest import mock

import torch


MODULE_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR / "src"))
sys.path.insert(0, str(MODULE_DIR))

import geometry as G  # noqa: E402
import graph  # noqa: E402
import server  # noqa: E402


class SettingsTests(unittest.TestCase):
    def test_bpe_bonus_counts_reused_module_occurrences_globally(self) -> None:
        shared = {
            "shapeType": "M_round_shared",
            "components": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
        }
        graphs = [
            graph.LayoutGraph(
                {"first": shared, "singleton": {"shapeType": "M_round_single"}},
                [],
                0,
            ),
            graph.LayoutGraph({"second": dict(shared)}, [], 1),
        ]
        self.assertEqual(server._reused_bpe_module_summary(graphs), (2, 6.0))

    def test_zero_angle_and_documented_learning_rate_are_valid(self) -> None:
        settings = server.validate_settings_patch(
            server.DEFAULT_SETTINGS,
            {"angleStep": 0.0, "learningRate": 0.001},
        )
        self.assertEqual(settings["angleStep"], 0.0)
        self.assertEqual(settings["learningRate"], 0.001)

    def test_invalid_transactions_do_not_mutate_input(self) -> None:
        original = dict(server.DEFAULT_SETTINGS)
        with self.assertRaises(server.SettingsError):
            server.validate_settings_patch(original, {"minEdge": 10.0, "maxEdge": 5.0})
        with self.assertRaises(server.SettingsError):
            server.validate_settings_patch(original, {"learningRate": 0.051})
        with self.assertRaises(server.SettingsError):
            server.validate_settings_patch(original, {"angleStep": 0.25})
        with self.assertRaises(server.SettingsError):
            server.validate_settings_patch(original, {"allowStop": "yes"})
        self.assertEqual(original, server.DEFAULT_SETTINGS)


class WeightedTopologyTests(unittest.TestCase):
    @staticmethod
    def make_environment() -> server.FloorEnvironment:
        boundary = G.make_boundary("rect", 7, {})
        site = G.build_site(boundary, [])
        return server.FloorEnvironment(0, boundary, {"id": "none", "holes": []}, site, (0.0, 0.0), G.RNG(9))

    @staticmethod
    def record(identifier: str, category: str, x: float) -> dict:
        poly = [
            {"x": x, "y": 0.0},
            {"x": x + 1.0, "y": 0.0},
            {"x": x + 1.0, "y": 1.0},
            {"x": x, "y": 1.0},
        ]
        return {"id": identifier, "category": category, "poly": poly, "center": {"x": x + 0.5, "y": 0.5}}

    def install_chain(self, categories: list[str]) -> tuple[server.FloorEnvironment, list[str]]:
        environment = self.make_environment()
        identifiers = []
        for index, category in enumerate(categories):
            identifier = f"n{index}"
            identifiers.append(identifier)
            record = self.record(identifier, category, float(index))
            environment.placements.append(record)
            environment.placement_by_id[identifier] = record
            environment.adjacency_map[identifier] = set()
            if index:
                prior = identifiers[index - 1]
                environment.adjacency_map[identifier].add(prior)
                environment.adjacency_map[prior].add(identifier)
        return environment, identifiers

    def test_two_intermediate_standard_rooms_pass_and_three_fail(self) -> None:
        two, ids = self.install_chain(["room", "room", "room", "core"])
        self.assertEqual(two._minimum_room_crossings(two.adjacency_map, ids[0]), 2)

        three, ids = self.install_chain(["room", "room", "room", "room", "core"])
        self.assertEqual(three._minimum_room_crossings(three.adjacency_map, ids[0]), 3)

    def test_transit_and_special_nodes_are_zero_cost(self) -> None:
        environment, ids = self.install_chain(["room", "corridor", "special", "corridor", "core"])
        self.assertEqual(environment._minimum_room_crossings(environment.adjacency_map, ids[0]), 0)


class SpatialBroadPhaseTests(unittest.TestCase):
    def test_distant_indexed_placement_skips_exact_overlap_query(self) -> None:
        boundary = G.make_boundary("rect", 17, {"boundaryWidth": 48.0, "boundaryHeight": 32.0})
        site = G.build_site(boundary, [])
        environment = server.FloorEnvironment(
            0,
            boundary,
            {"id": "none", "holes": []},
            site,
            (0.0, 0.0),
            G.RNG(17),
        )

        near = {
            "id": "near",
            "category": "room",
            "poly": [
                {"x": 10.0, "y": 8.0},
                {"x": 12.0, "y": 8.0},
                {"x": 12.0, "y": 10.0},
                {"x": 10.0, "y": 10.0},
            ],
            "center": {"x": 11.0, "y": 9.0},
        }
        distant = {
            "id": "distant",
            "category": "room",
            "poly": [
                {"x": 32.0, "y": 8.0},
                {"x": 34.0, "y": 8.0},
                {"x": 34.0, "y": 10.0},
                {"x": 32.0, "y": 10.0},
            ],
            "center": {"x": 33.0, "y": 9.0},
        }
        for placement in (near, distant):
            environment.placements.append(placement)
            environment.placement_by_id[placement["id"]] = placement
            environment._index_placement(placement)

        module = {"id": "candidate-room", "category": "room", "area": 4.0}
        rotation = {
            "angle": 0.0,
            "poly": [
                {"x": 0.0, "y": 0.0},
                {"x": 2.0, "y": 0.0},
                {"x": 2.0, "y": 2.0},
                {"x": 0.0, "y": 2.0},
            ],
        }
        queried_placements: list[list[dict]] = []
        exact_overlap = G.polygons_overlap

        def track_exact_overlap(candidate_poly: list[dict], placement_poly: list[dict]) -> bool:
            queried_placements.append(placement_poly)
            return exact_overlap(candidate_poly, placement_poly)

        with mock.patch.object(G, "polygons_overlap", side_effect=track_exact_overlap):
            candidate = environment._candidate_from_anchor(
                module,
                rotation,
                8.0,
                8.0,
                server.DEFAULT_SETTINGS,
                0.0,
                {},
            )

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.neighbors, ["near"])
        self.assertEqual(len(queried_placements), 1)
        self.assertIs(queried_placements[0], near["poly"])
        self.assertTrue(all(poly is not distant["poly"] for poly in queried_placements))


class AttachmentFrontierTests(unittest.TestCase):
    @staticmethod
    def _environment() -> server.FloorEnvironment:
        boundary = G.make_boundary(
            "rect",
            29,
            {"boundaryWidth": 48.0, "boundaryHeight": 32.0},
        )
        site = G.build_site(boundary, [])
        return server.FloorEnvironment(
            0,
            boundary,
            {"id": "none", "holes": []},
            site,
            (0.0, 0.0),
            G.RNG(29),
        )

    @staticmethod
    def _install(environment: server.FloorEnvironment, placement: dict) -> None:
        environment.placements.append(placement)
        environment.placement_by_id[placement["id"]] = placement
        environment._index_placement(placement)

    def test_centered_partial_wall_contact_preserves_residuals_and_filters_bad_ratio(self) -> None:
        environment = self._environment()
        wall = {
            "id": "nine-meter-wall",
            "poly": [
                {"x": 0.0, "y": 0.0},
                {"x": 9.0, "y": 0.0},
                {"x": 9.0, "y": 2.0},
                {"x": 0.0, "y": 2.0},
            ],
        }
        wall_module = {
            "connectionEdge": {"index": 0, "oppositeIndex": 2},
        }
        self._install(environment, wall)
        environment._update_attachment_frontier(wall, wall_module, [])

        centered_contact = {
            "id": "centered-contact",
            "poly": [
                {"x": 4.0, "y": -1.0},
                {"x": 5.0, "y": -1.0},
                {"x": 5.0, "y": 0.0},
                {"x": 4.0, "y": 0.0},
            ],
        }
        contact_module = {
            "connectionEdge": {"index": 0, "oppositeIndex": 2},
        }
        self._install(environment, centered_contact)
        environment._update_attachment_frontier(
            centered_contact,
            contact_module,
            [wall["id"]],
        )

        residuals = [
            edge
            for edge in environment.attachment_edges.values()
            if edge["placementId"] == wall["id"]
            and edge["a"]["y"] == 0.0
            and edge["b"]["y"] == 0.0
        ]
        residual_intervals = sorted(
            (
                min(edge["a"]["x"], edge["b"]["x"]),
                max(edge["a"]["x"], edge["b"]["x"]),
            )
            for edge in residuals
        )
        self.assertEqual(residual_intervals, [(0.0, 4.0), (5.0, 9.0)])
        self.assertAlmostEqual(sum(edge["length"] for edge in residuals), 8.0, places=7)
        self.assertTrue(all(edge["length"] >= server.MIN_SHARED_EDGE for edge in residuals))

        candidate_module = {
            "connectionEdge": {"index": 0, "oppositeIndex": 2},
        }
        candidate_rotation = {
            "poly": [
                {"x": 0.0, "y": 0.0},
                {"x": 1.0, "y": 0.0},
                {"x": 1.0, "y": 1.0},
                {"x": 0.0, "y": 1.0},
            ],
        }
        anchors = {
            (round(anchor_x, 7), round(anchor_y, 7))
            for anchor_x, anchor_y in environment._edge_alignment_anchors(
                candidate_module,
                candidate_rotation,
            )
        }
        # The residual geometry remains available for future compatible
        # modules, but a 1m candidate against the original 9m wall cannot pass
        # the exact 1:1 / 1:2 / 2:1 alignment contract and is pruned early.
        self.assertNotIn((1.5, 0.0), anchors)
        self.assertNotIn((6.5, 0.0), anchors)


class ParallelTrainerTests(unittest.TestCase):
    def setUp(self) -> None:
        torch.manual_seed(1234)

    def make_trainer(self, environment_count: int = 2) -> server.ParallelTrainer:
        trainer = server.ParallelTrainer()
        event = trainer.update_settings(
            {
                "boundaryType": "rect",
                "atriumPolicy": "none",
                "parallelEnvironments": environment_count,
                "maxModules": 10,
                "dictCap": 6,
                "angleStep": 90.0,
                "seed": 812,
            }
        )
        self.assertEqual(event["type"], "site")
        return trainer

    def test_dynamic_environments_share_one_dictionary(self) -> None:
        trainer = self.make_trainer(3)
        event = trainer.site_event()
        self.assertEqual(len(event["boundaries"]), 3)
        self.assertEqual(len(event["dictionary"]), 0)
        self.assertTrue(all(environment.dictionary is not trainer.dictionary for environment in trainer.environments))
        self.assertTrue(all(environment.dictionary == trainer.dictionary for environment in trainer.environments))

    def test_first_batched_step_places_a_core_on_every_floor(self) -> None:
        trainer = self.make_trainer(2)
        event = trainer.step(trainer.generation_id, trainer.episode)
        self.assertEqual(event["type"], "placements")
        self.assertEqual(len(event["placements"]), 2)
        self.assertTrue(all(item["module"]["category"] == "core" for item in event["placements"]))
        self.assertEqual(event["metrics"]["moduleCount"], 2)
        expected_fill = sum(item["area"] for item in event["placements"])
        self.assertAlmostEqual(event["metrics"]["filledArea"], expected_fill, places=6)

    def test_stale_step_is_rejected_before_mutation(self) -> None:
        trainer = self.make_trainer(1)
        with self.assertRaises(server.StaleStepError):
            trainer.step(trainer.generation_id - 1, trainer.episode)
        self.assertEqual(trainer.step_number, 0)
        self.assertFalse(trainer.environments[0].placements)

    def test_zero_angle_increment_can_grow_beyond_the_first_core(self) -> None:
        trainer = server.ParallelTrainer()
        trainer.update_settings(
            {
                "boundaryType": "rect",
                "atriumPolicy": "none",
                "parallelEnvironments": 1,
                "maxModules": 10,
                "dictCap": 8,
                "angleStep": 0.0,
                "seed": 508,
            }
        )
        first = trainer.step(trainer.generation_id, trainer.episode)
        second = trainer.step(trainer.generation_id, trainer.episode)
        self.assertEqual(first["type"], "placements")
        self.assertEqual(second["type"], "placements")
        self.assertEqual(second["metrics"]["moduleCount"], 2)

    def test_three_edge_cap_and_zero_increment_remain_connectable(self) -> None:
        trainer = server.ParallelTrainer()
        trainer.update_settings(
            {
                "boundaryType": "rect",
                "atriumPolicy": "none",
                "parallelEnvironments": 1,
                "maxModules": 10,
                "dictCap": 6,
                "maxEdges": 3,
                "angleStep": 0.0,
                "maxEdge": 9.0,
                "seed": 1881,
            }
        )
        first = trainer.step(trainer.generation_id, trainer.episode)
        second = trainer.step(trainer.generation_id, trainer.episode)
        self.assertEqual(first["type"], "placements")
        self.assertEqual(second["type"], "placements")
        self.assertEqual(second["metrics"]["moduleCount"], 2)

    def test_beam_search_inference_and_trajectory_recording(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            trainer = server.ParallelTrainer()
            trainer.update_settings(
                {
                    "boundaryType": "rect",
                    "atriumPolicy": "none",
                    "parallelEnvironments": 1,
                    "maxModules": 10,
                    "dictCap": 6,
                    "beamSearchWidth": 3,
                    "recordTrajectories": True,
                    "seed": 42,
                }
            )
            for _ in range(40):
                event = trainer.step(trainer.generation_id, trainer.episode)
                if event["type"] == "episodeDone":
                    break
            self.assertEqual(event["type"], "episodeDone")
            out_file = os.path.join(tmpdir, "test_dataset.jsonl")
            path = server.record_dataset_trajectory(event, data_dir=tmpdir, filename="test_dataset.jsonl")
            self.assertTrue(os.path.exists(out_file))
            with open(out_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            self.assertEqual(len(lines), 1)
            loaded = json.loads(lines[0])
            self.assertIn("score", loaded)
            self.assertIn("placements", loaded)


if __name__ == "__main__":
    unittest.main()

