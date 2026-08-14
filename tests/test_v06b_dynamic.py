"""v0.6-B dynamic palette and relative-frontier reward regressions."""

from __future__ import annotations

import math
import pathlib
import sys
import unittest

import torch


MODULE_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR / "src"))
sys.path.insert(0, str(MODULE_DIR))

import geometry as G  # noqa: E402
import graph  # noqa: E402
import server  # noqa: E402


class DynamicPaletteTests(unittest.TestCase):
    def setUp(self) -> None:
        torch.manual_seed(611)

    def test_five_and_ten_degree_palettes_stay_snapped_and_valid(self) -> None:
        for step in (5.0, 10.0):
            settings = server.validate_settings_patch(server.DEFAULT_SETTINGS, {"angleStep": step})
            proposals = G.enumerate_parametric_proposals(settings, "room")
            self.assertGreater(len(proposals), 100)
            self.assertIn("irregular_quad", {item["shapeType"] for item in proposals})
            self.assertEqual(
                len(proposals),
                len({item["geometrySignature"] for item in proposals}),
            )
            self.assertTrue(all(abs(item["angle"] / step - round(item["angle"] / step)) < 1.0e-8 for item in proposals))
            for proposal in proposals:
                poly = G._parametric_polygon(
                    proposal["shapeType"],
                    proposal["width"],
                    proposal["height"],
                    proposal["angle"],
                )
                self.assertTrue(
                    all(
                        min(abs(edge - palette_edge) for palette_edge in G.EDGE_PALETTE) < 1.0e-6
                        for edge in G._edge_lengths(poly)
                    )
                )
                self.assertTrue(
                    all(
                        abs(angle / step - round(angle / step)) < 1.0e-6
                        for angle in G.internal_angles(poly)
                    )
                )
            selected = next(item for item in proposals if item["shapeType"] == "parallelogram")
            module = G.synthesize_parametric_module(
                settings,
                "room",
                selected["widthIndex"],
                selected["heightIndex"],
                selected["angleIndex"],
                selected["typeIndex"],
                "dynamic-test",
            )
            self.assertEqual(module["family"], "dynamic-palette")
            self.assertEqual(module["parameters"]["generator"], "discrete-palette")
            self.assertGreater(min(module["parameters"]["internalAngles"]), 40.0)
            self.assertGreaterEqual(min(module["parameters"]["edgeLengths"]), settings["minEdge"] - 1.0e-7)
            self.assertLessEqual(max(module["parameters"]["edgeLengths"]), settings["maxEdge"] + 1.0e-7)

    def test_geometry_identity_ignores_rotation_and_action_spelling_but_not_reflection(self) -> None:
        rectangle = G._parametric_polygon("rectangle", 3.0, 4.0, 90.0)
        swapped = G._parametric_polygon("rectangle", 4.0, 3.0, 90.0)
        rotated = G.rotate_polygon(rectangle, 35.0, origin={"x": 0.0, "y": 0.0})
        self.assertEqual(
            G.rotation_only_polygon_signature(rectangle),
            G.rotation_only_polygon_signature(swapped),
        )
        self.assertEqual(
            G.rotation_only_polygon_signature(rectangle),
            G.rotation_only_polygon_signature(rotated),
        )
        irregular_proposal = next(
            item
            for item in G.enumerate_parametric_proposals(
                server.validate_settings_patch(server.DEFAULT_SETTINGS, {"angleStep": 5.0}),
                "room",
            )
            if item["shapeType"] == "irregular_quad"
        )
        irregular = G._parametric_polygon(
            "irregular_quad",
            irregular_proposal["width"],
            irregular_proposal["height"],
            irregular_proposal["angle"],
        )
        mirrored = [{"x": -point["x"], "y": point["y"]} for point in irregular]
        self.assertNotEqual(
            G.rotation_only_polygon_signature(irregular),
            G.rotation_only_polygon_signature(mirrored),
        )

    def test_bpe_identity_does_not_collapse_five_and_ten_degree_joins(self) -> None:
        first = {
            "id": "a",
            "moduleId": "dynamic-a",
            "shapeType": "dynamic-a",
            "poly": G._parametric_polygon("rectangle", 3.0, 4.0, 90.0),
            "rotation": 0.0,
        }
        source = G.translate_polygon(
            G._parametric_polygon("irregular_quad", G.EDGE_PALETTE[2], 2.0, 60.0),
            5.0,
            0.0,
        )
        connection = graph.EdgeConnection(
            "a",
            "b",
            0,
            0,
            {"x": 0.0, "y": 0.0},
            {"x": 1.0, "y": 0.0},
            1.0,
            1.0,
        )
        keys = []
        for angle in (5.0, 10.0):
            second = {
                "id": "b",
                "moduleId": "dynamic-b",
                "shapeType": "dynamic-b",
                "poly": G.rotate_polygon(
                    source,
                    angle,
                    origin=G.polygon_centroid(source),
                    normalize=False,
                ),
                "rotation": angle,
            }
            layout = graph.LayoutGraph({"a": first, "b": second}, [], 0)
            keys.append(graph.canonicalize_merge_key(connection, layout))
        self.assertNotEqual(keys[0], keys[1])
        self.assertNotEqual(keys[0].geometry_signature, keys[1].geometry_signature)

    def test_dynamic_dictionary_starts_empty_and_custom_action_is_learnable(self) -> None:
        trainer = server.ParallelTrainer()
        trainer.update_settings(
            {
                "boundaryType": "rect",
                "atriumPolicy": "none",
                "parallelEnvironments": 1,
                "maxModules": 10,
                "dictCap": 8,
                "angleStep": 5.0,
                "seed": 606,
            }
        )
        self.assertEqual(trainer.dictionary, [])
        self.assertEqual(trainer.shape_log_probs, [])

        module, log_probability = trainer._sample_custom_shape(
            trainer.settings, trainer.environments, 0
        )
        self.assertIn(len(module["poly"]), (3, 4))
        self.assertTrue(module["learnedGeometry"])
        self.assertIn("latent", module["parameters"])
        self.assertGreaterEqual(module["area"], 24.0)
        self.assertTrue(
            all(
                trainer.settings["minEdge"] - 1.0e-4
                <= length
                <= trainer.settings["maxEdge"] + 1.0e-4
                for length in G._edge_lengths(module["poly"])
            )
        )
        self.assertGreaterEqual(len(module["rotations"]), 1)
        self.assertLessEqual(len(module["rotations"]), 72)
        self.assertTrue(
            all(
                abs(rotation["angle"] / 5.0 - round(rotation["angle"] / 5.0)) < 1.0e-8
                for rotation in module["rotations"]
            )
        )
        self.assertTrue(log_probability.requires_grad)

    def test_fine_angle_rotation_counts_are_fully_materialized(self) -> None:
        trainer = server.ParallelTrainer()
        for step, expected_count in ((5.0, 72), (10.0, 36)):
            settings = server.validate_settings_patch(server.DEFAULT_SETTINGS, {"angleStep": step})
            proposal = next(
                item
                for item in G.enumerate_parametric_proposals(settings, "room")
                if item["shapeType"] == "irregular_quad"
            )
            module = G.synthesize_parametric_module(
                settings,
                "room",
                proposal["widthIndex"],
                proposal["heightIndex"],
                proposal["angleIndex"],
                proposal["typeIndex"],
                f"rotations-{int(step)}",
            )
            canonical = trainer._canonical_module(module, step, phase=0)
            self.assertEqual(len(canonical["rotations"]), expected_count)
            self.assertTrue(
                all(
                    abs(rotation["angle"] / step - round(rotation["angle"] / step)) < 1.0e-8
                    for rotation in canonical["rotations"]
                )
            )

    def test_terminal_learning_updates_actor_shape_policy_and_critic(self) -> None:
        trainer = server.ParallelTrainer()
        trainer.update_settings(
            {
                "boundaryType": "rect",
                "atriumPolicy": "none",
                "parallelEnvironments": 1,
                "maxModules": 10,
                "dictCap": 6,
                "angleStep": 10.0,
                "seed": 609,
            }
        )
        heads = {
            "placement": trainer.model.placement_head,
            "shape": trainer.model.shape_head,
            "numEdges": trainer.model.num_edges_head,
            "critic": trainer.model.value_head,
        }
        before = {
            name: [parameter.detach().clone() for parameter in head.parameters()]
            for name, head in heads.items()
        }
        for _ in range(30):
            event = trainer.step(trainer.generation_id, trainer.episode)
            if event["type"] == "episodeDone":
                break
        self.assertEqual(event["type"], "episodeDone")
        self.assertNotEqual(event["metrics"]["policyLoss"], 0.0)
        self.assertEqual(
            event["metrics"]["learningAlgorithm"], "ppo_gae"
        )
        self.assertGreaterEqual(event["metrics"]["valueLoss"], 0.0)
        self.assertTrue(math.isfinite(event["metrics"]["gradientNorm"]))
        for name, head in heads.items():
            self.assertTrue(
                any(
                    not torch.equal(prior, current.detach())
                    for prior, current in zip(before[name], head.parameters())
                ),
                name,
            )
            self.assertTrue(
                all(torch.isfinite(parameter).all() for parameter in head.parameters())
            )

    def test_root_geometry_limits_are_transactional_and_exposed_by_controls(self) -> None:
        for patch in (
            {"minEdge": 0.5},
            {"maxEdge": 9.5},
            {"maxEdges": 9},
            {"maxEdge": 3.0, "maxEdges": 8},
        ):
            with self.subTest(patch=patch), self.assertRaises(server.SettingsError):
                server.validate_settings_patch(server.DEFAULT_SETTINGS, patch)
        public_dir = (MODULE_DIR / "public") if (MODULE_DIR / "public" / "index.html").is_file() else MODULE_DIR
        html = (public_dir / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="minEdge" name="minEdge" type="range" min="1" max="9"', html)
        self.assertIn('id="maxEdge" name="maxEdge" type="range" min="1" max="9"', html)
        self.assertIn('id="maxEdges" name="maxEdges" type="range" min="3" max="8"', html)

    def test_single_floor_is_room_only_and_triangle_penalty_is_canonical(self) -> None:
        trainer = server.ParallelTrainer()
        site = trainer.update_settings(
            {
                "singleFloor": True,
                "parallelEnvironments": 2,
                "maxModules": 10,
                "dictCap": 5,
                "seed": 612,
            }
        )
        self.assertTrue(all(module["category"] == "room" for module in site["dictionary"]))
        event = trainer.step(trainer.generation_id, trainer.episode)
        self.assertTrue(all(item["module"]["category"] == "room" for item in event["placements"]))
        self.assertTrue(
            all(
                environment.validate_topology(True, trainer.settings["coreSpacing"])[0]
                for environment in trainer.environments
            )
        )
        self.assertEqual(server._average_unmerged_triangle_penalty(3, 2), 12.0)

    def test_single_floor_ignores_disabled_core_and_corridor_feasibility(self) -> None:
        compact = server.validate_settings_patch(
            server.DEFAULT_SETTINGS,
            {
                "singleFloor": True,
                "minEdge": 1.0,
                "maxEdge": 3.0,
                "maxEdges": 4,
            },
        )
        self.assertTrue(compact["singleFloor"])
        wide_minimum = server.validate_settings_patch(
            server.DEFAULT_SETTINGS,
            {
                "singleFloor": True,
                "minEdge": 2.5,
                "maxEdge": 3.0,
                "maxEdges": 4,
            },
        )
        self.assertEqual(wide_minimum["minEdge"], 2.5)
        with self.assertRaises(server.SettingsError):
            server.validate_settings_patch(
                server.DEFAULT_SETTINGS,
                {
                    "singleFloor": False,
                    "minEdge": 1.0,
                    "maxEdge": 3.0,
                    "maxEdges": 4,
                },
            )

        trainer = server.ParallelTrainer()
        site = trainer.update_settings(compact)
        self.assertEqual(site["dictionary"], [])
        trainer.step(trainer.generation_id, trainer.episode)
        self.assertTrue(trainer.environments[0].placements)
        self.assertEqual(
            {placement["category"] for placement in trainer.environments[0].placements},
            {"room"},
        )


class RelativeFrontierRewardTests(unittest.TestCase):
    def test_rotation_action_multiplicity_cannot_inflate_frontier_proxy(self) -> None:
        trainer = server.ParallelTrainer()
        trainer.update_settings(
            {
                "boundaryType": "rect",
                "atriumPolicy": "none",
                "parallelEnvironments": 1,
                "maxModules": 10,
                "dictCap": 6,
            }
        )
        environment = trainer.environments[0]
        environment.last_unique_frontier_count = 5
        environment.last_candidate_evaluations = 100
        trainer._record_frontier_sample(environment, 1.0)
        first_time = trainer.episode_action_normalized_seconds
        first_growth = trainer.episode_frontier_growth

        trainer._reset_episode_reward_telemetry()
        environment.last_unique_frontier_count = 5
        environment.last_candidate_evaluations = 200
        trainer._record_frontier_sample(environment, 2.0)
        self.assertAlmostEqual(trainer.episode_action_normalized_seconds, first_time)
        self.assertAlmostEqual(trainer.episode_frontier_growth, first_growth)

    def test_rolling_baseline_and_setting_transition_are_bounded(self) -> None:
        trainer = server.ParallelTrainer()
        trainer.update_settings(
            {
                "boundaryType": "rect",
                "atriumPolicy": "none",
                "parallelEnvironments": 1,
                "maxModules": 10,
                "dictCap": 6,
                "seed": 607,
            }
        )
        environment = trainer.environments[0]
        environment.placements = [
            {
                "id": "reward-probe",
                "area": 12.0,
                "poly": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 4.0, "y": 0.0},
                    {"x": 4.0, "y": 3.0},
                    {"x": 0.0, "y": 3.0},
                ],
            }
        ]
        trainer.episode_generation_seconds = 1.0
        trainer.episode_action_normalized_seconds = 1.0
        trainer.episode_frontier_growth = 4.0
        trainer.episode_frontier_samples = 1
        first = trainer._relative_frontier_reward()
        self.assertAlmostEqual(first["relativeTimeReward"], 0.0)

        trainer.episode_generation_seconds = 1.5
        trainer.episode_action_normalized_seconds = 1.5
        trainer.episode_frontier_growth = 6.0
        trainer.episode_frontier_samples = 1
        improved = trainer._relative_frontier_reward()
        self.assertGreater(improved["relativeTimeReward"], 0.0)
        self.assertLessEqual(abs(improved["relativeTimeReward"]), server.MAX_FRONTIER_REWARD)

        trainer.update_settings({"maxModules": 11})
        self.assertEqual(trainer.baseline_transition_remaining, server.BASELINE_TRANSITION_EPISODES)
        self.assertIsNotNone(trainer.generation_time_baseline)

        anchor = trainer.baseline_transition_anchor_reward
        blended_rewards = []
        for transition_index in range(server.BASELINE_TRANSITION_EPISODES):
            trainer.episode_generation_seconds = 100.0
            trainer.episode_action_normalized_seconds = 100.0
            trainer.episode_frontier_growth = 400.0
            trainer.episode_frontier_samples = 1
            transition_metrics = trainer._relative_frontier_reward()
            blended_rewards.append(transition_metrics["relativeTimeReward"])
            expected_progress = (transition_index + 1) / server.BASELINE_TRANSITION_EPISODES
            expected_reward = (
                (1.0 - expected_progress) * anchor
                + expected_progress * transition_metrics["unblendedRelativeTimeReward"]
            )
            self.assertAlmostEqual(transition_metrics["relativeTimeReward"], expected_reward, places=7)
        self.assertAlmostEqual(
            blended_rewards[-1],
            transition_metrics["unblendedRelativeTimeReward"],
            places=7,
        )

        trainer.new_site()
        self.assertEqual(trainer.baseline_transition_remaining, server.BASELINE_TRANSITION_EPISODES)
        trainer.update_settings({"coreSpacing": 9.0, "seed": 608})
        self.assertEqual(trainer.baseline_transition_remaining, server.BASELINE_TRANSITION_EPISODES)

    def test_reward_metrics_are_exposed_in_score_breakdown(self) -> None:
        public_dir = (MODULE_DIR / "public") if (MODULE_DIR / "public" / "app.js").is_file() else MODULE_DIR
        app_source = (public_dir / "app.js").read_text(encoding="utf-8")
        self.assertIn("metrics.relativeTimeReward", app_source)
        self.assertIn("metrics.frontierGrowthPotential", app_source)
        self.assertIn("metrics.generationTimeReferenceUsed", app_source)
        self.assertIn("Relative Frontier / Time Reward", app_source)


if __name__ == "__main__":
    unittest.main()
