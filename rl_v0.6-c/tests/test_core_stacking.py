"""Focused v0.6-C regressions for atomic multi-floor core stacking."""

from __future__ import annotations

import copy
import pathlib
import sys
import unittest
from unittest import mock

import torch


MODULE_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

import geometry as G  # noqa: E402
import server  # noqa: E402


class CoreStackingGeometryTests(unittest.TestCase):
    @staticmethod
    def _boundary(outer: list[dict[str, float]], family: str) -> dict:
        return {"outer": outer, "type": family, "family": family, "parameters": {}}

    def test_incompatible_concavities_use_a_reported_envelope_fallback(self) -> None:
        lower_left_l = self._boundary(
            [
                {"x": 0.0, "y": 0.0},
                {"x": 12.0, "y": 0.0},
                {"x": 12.0, "y": 3.0},
                {"x": 3.0, "y": 3.0},
                {"x": 3.0, "y": 12.0},
                {"x": 0.0, "y": 12.0},
            ],
            "lower-left-L",
        )
        upper_right_l = self._boundary(
            [
                {"x": 9.0, "y": 0.0},
                {"x": 12.0, "y": 0.0},
                {"x": 12.0, "y": 12.0},
                {"x": 0.0, "y": 12.0},
                {"x": 0.0, "y": 9.0},
                {"x": 9.0, "y": 9.0},
            ],
            "upper-right-L",
        )

        adapted, metadata = G.adapt_boundaries_for_core_reserve(
            [lower_left_l, upper_right_l], 4.0, 4.0
        )

        self.assertEqual(metadata["status"], "ready")
        self.assertEqual(metadata["mode"], "envelope-fallback")
        self.assertEqual(metadata["adaptedBoundaryIndices"], [0, 1])
        self.assertEqual(metadata["failureSafe"], "reject-generation-atomically")
        self.assertTrue(
            all(
                G.polygon_inside_site(metadata["poly"], boundary["outer"], [])
                for boundary in adapted
            )
        )

    def test_atrium_filter_removes_only_candidates_that_block_reserve(self) -> None:
        boundary = G.make_boundary(
            "rect", 71, {"boundaryWidth": 12.0, "boundaryHeight": 12.0}
        )
        reserve = [
            {"x": 4.0, "y": 4.0},
            {"x": 8.0, "y": 4.0},
            {"x": 8.0, "y": 8.0},
            {"x": 4.0, "y": 8.0},
        ]
        blocked = {
            "id": "blocked",
            "holes": [
                [
                    {"x": 5.0, "y": 5.0},
                    {"x": 7.0, "y": 5.0},
                    {"x": 7.0, "y": 7.0},
                    {"x": 5.0, "y": 7.0},
                ]
            ],
        }
        clear = {
            "id": "clear",
            "holes": [
                [
                    {"x": 0.5, "y": 0.5},
                    {"x": 2.0, "y": 0.5},
                    {"x": 2.0, "y": 2.0},
                    {"x": 0.5, "y": 2.0},
                ]
            ],
        }

        accepted, rejected = G.atrium_candidates_clear_of_reserve(
            boundary,
            [{"id": "none", "holes": []}, blocked, clear],
            reserve,
        )

        self.assertEqual([candidate["id"] for candidate in accepted], ["none", "clear"])
        self.assertEqual(rejected, ["blocked"])


class ParallelCoreStackingTests(unittest.TestCase):
    def setUp(self) -> None:
        torch.manual_seed(20260720)

    def _trainer(
        self,
        floors: int = 3,
        boundary_type: str = "rect",
        atrium_policy: str = "none",
    ) -> server.ParallelTrainer:
        trainer = server.ParallelTrainer()
        event = trainer.update_settings(
            {
                "boundaryType": boundary_type,
                "atriumPolicy": atrium_policy,
                "parallelEnvironments": floors,
                "maxModules": 10,
                "dictCap": 6,
                "angleStep": 90.0,
                "seed": 906,
            }
        )
        self.assertEqual(event["stacking"]["status"], "ready")
        return trainer

    def test_first_core_is_one_policy_action_and_exact_on_three_floors(self) -> None:
        trainer = self._trainer(3)

        event = trainer.step(trainer.generation_id, trainer.episode)

        self.assertEqual(len(event["placements"]), 3)
        self.assertEqual(len(trainer.placement_log_probs), 1)
        self.assertEqual(event["stacking"]["stackCount"], 1)
        self.assertEqual(event["metrics"]["coreStacking"]["lockedCoreCount"], 3)
        self.assertTrue(event["metrics"]["coreStacking"]["exactLocalAlignment"])
        self.assertTrue(
            all(
                placement["localPoly"] == event["placements"][0]["localPoly"]
                for placement in event["placements"][1:]
            )
        )
        cores = [environment.placements[0] for environment in trainer.environments]
        self.assertEqual(len({core["moduleId"] for core in cores}), 1)
        self.assertEqual(len({core["rotation"] for core in cores}), 1)
        self.assertEqual(len({core["coreStackId"] for core in cores}), 1)
        self.assertTrue(all(core["coreStackLocked"] for core in cores))
        self.assertTrue(all(core["poly"] == cores[0]["poly"] for core in cores[1:]))
        self.assertTrue(
            all(core["localAnchor"] == cores[0]["localAnchor"] for core in cores[1:])
        )
        self.assertTrue(
            all(
                G.polygon_inside_site(core["poly"], environment.site["outer"], environment.site["holes"])
                for core, environment in zip(cores, trainer.environments)
            )
        )

    def test_shared_stack_uses_one_pooled_building_policy_term(self) -> None:
        trainer = self._trainer(3)
        stacks = trainer._shared_core_stack_candidates(0.0)
        self.assertGreater(len(stacks), 1)
        target_index = len(stacks) - 1
        observed_features: list[torch.Tensor] = []

        def force_building_stack(features: torch.Tensor) -> torch.Tensor:
            observed_features.append(features.detach().cpu())
            values = [-30.0] * len(stacks)
            values[target_index] = 30.0
            self.assertEqual(len(values), features.shape[0])
            return torch.tensor(
                values,
                dtype=torch.float32,
                device=trainer.device,
                requires_grad=True,
            )

        with mock.patch.object(
            trainer.model,
            "placement_logits",
            side_effect=force_building_stack,
        ) as placement_logits:
            event = trainer.step(trainer.generation_id, trainer.episode)

        expected_features = torch.tensor(
            [
                server._mean_feature_rows(
                    [candidate.features for candidate in stack.floor_candidates]
                )
                for stack in stacks
            ],
            dtype=torch.float32,
        )
        self.assertEqual(placement_logits.call_count, 1)
        self.assertTrue(torch.allclose(observed_features[0], expected_features))
        self.assertEqual(len(event["placements"]), 3)
        self.assertIsNone(event["stackDecision"]["triggerFloor"])
        self.assertEqual(event["stackDecision"]["decisionScope"], "building")
        self.assertEqual(event["stackDecision"]["policyCandidateCount"], len(stacks))
        self.assertEqual(len(trainer.placement_log_probs), 1)
        temperature = 0.90
        expected_logits = torch.tensor(
            [-30.0] * target_index + [30.0], dtype=torch.float32
        )
        expected_log_prob = torch.distributions.Categorical(
            logits=expected_logits / temperature
        ).log_prob(torch.tensor(target_index))
        self.assertTrue(
            torch.allclose(
                trainer.placement_log_probs[0].detach().cpu(), expected_log_prob
            )
        )
        self.assertTrue(
            all(
                environment.placements[0]["coreStackTriggerFloor"] is None
                for environment in trainer.environments
            )
        )
        local_polys = [environment.placements[0]["poly"] for environment in trainer.environments]
        self.assertTrue(all(poly == local_polys[0] for poly in local_polys[1:]))

    def test_no_stack_branch_precedes_independent_room_actions(self) -> None:
        trainer = self._trainer(3)
        trainer.step(trainer.generation_id, trainer.episode)
        terms_before = len(trainer.placement_log_probs)
        self.assertTrue(trainer._shared_core_stack_candidates(0.0))
        calls = 0

        def force_no_stack(features: torch.Tensor) -> torch.Tensor:
            nonlocal calls
            calls += 1
            if calls == 1:
                values = [30.0] + [-30.0] * (features.shape[0] - 1)
            else:
                values = [0.0] * features.shape[0]
            return torch.tensor(
                values,
                dtype=torch.float32,
                device=trainer.device,
                requires_grad=True,
            )

        with mock.patch.object(
            trainer.model,
            "placement_logits",
            side_effect=force_no_stack,
        ) as placement_logits:
            event = trainer.step(trainer.generation_id, trainer.episode)

        self.assertEqual(placement_logits.call_count, 2)
        self.assertIsNone(event["stackDecision"])
        self.assertEqual(len(event["placements"]), 3)
        self.assertTrue(
            all(item["module"]["category"] == "room" for item in event["placements"])
        )
        # One true no-stack term plus one independent placement term per floor.
        self.assertEqual(
            len(trainer.placement_log_probs),
            terms_before + 1 + len(trainer.environments),
        )

    def test_stale_stack_blocked_on_one_floor_mutates_no_other_floor(self) -> None:
        trainer = self._trainer(3)
        stack = trainer._shared_core_stack_candidates(0.0)[0]
        blocked_floor = trainer.environments[1]
        blocked_poly = copy.deepcopy(stack.floor_candidates[1].poly)
        blocker = {
            "id": "test-blocker",
            "category": "room",
            "poly": blocked_poly,
            "center": G.polygon_centroid(blocked_poly),
        }
        blocked_floor.placements.append(blocker)
        blocked_floor.placement_by_id[blocker["id"]] = blocker
        blocked_floor._index_placement(blocker)
        counts_before = [len(environment.placements) for environment in trainer.environments]

        with self.assertRaises(server.CoreStackingError):
            trainer._commit_core_stack(stack, trigger_floor=1)

        self.assertEqual(
            [len(environment.placements) for environment in trainer.environments],
            counts_before,
        )
        self.assertFalse(trainer.core_stack_records)
        self.assertFalse(trainer.placement_log_probs)

    def test_room_frontiers_grow_from_locked_core_anchors(self) -> None:
        trainer = self._trainer(3)
        trainer.step(trainer.generation_id, trainer.episode)

        candidate_groups = []
        for environment in trainer.environments:
            candidates = environment.generate_candidates(
                trainer.settings,
                0.0,
                limit=24,
                allowed_categories={"room"},
            )
            candidate_groups.append(candidates)
            self.assertTrue(
                all(
                    set(candidate.neighbors).intersection(environment.core_ids)
                    for candidate in candidates
                )
            )
        self.assertTrue(
            any(candidate_groups),
            [
                (module["id"], module["category"], module.get("name"))
                for module in trainer.dictionary
            ],
        )

    def test_single_floor_disables_structural_categories_and_metrics(self) -> None:
        trainer = server.ParallelTrainer()
        site = trainer.update_settings(
            {
                "singleFloor": True,
                "parallelEnvironments": 2,
                "maxModules": 10,
                "dictCap": 5,
                "seed": 42,
            }
        )

        self.assertEqual(site["stacking"]["status"], "disabled-single-floor-mode")
        self.assertNotIn("coreStacking", site["metrics"])
        self.assertEqual(
            {module["category"] for module in site["dictionary"]}, {"room"}
        )
        event = trainer.step(trainer.generation_id, trainer.episode)
        self.assertEqual(len(event["placements"]), 2)
        self.assertTrue(
            all(item["module"]["category"] == "room" for item in event["placements"])
        )
        self.assertNotIn("coreStacking", event["metrics"])
        self.assertTrue(
            all(
                environment.validate_topology(True, trainer.settings["coreSpacing"])[0]
                for environment in trainer.environments
            )
        )

    def test_stacking_metric_detects_local_anchor_mismatch(self) -> None:
        trainer = self._trainer(3)
        trainer.step(trainer.generation_id, trainer.episode)
        trainer.environments[1].placements[0]["localAnchor"]["x"] += 0.5

        event = trainer._stacking_event()

        self.assertFalse(event["exactLocalAlignment"])
        self.assertTrue(
            any(violation.endswith(":anchorMismatch") for violation in event["violations"])
        )

    def test_next_episode_stack_failure_precedes_all_episode_mutation(self) -> None:
        trainer = self._trainer(3)
        trainer.step(trainer.generation_id, trainer.episode)
        episode_before = trainer.episode
        baseline_before = trainer.baseline
        history_before = list(trainer.score_history)
        dictionary_before = trainer.dictionary
        placements_before = copy.deepcopy(
            [environment.placements for environment in trainer.environments]
        )

        with mock.patch.object(
            trainer,
            "_initial_stacks_on_empty_floors",
            return_value=[],
        ):
            with self.assertRaises(server.CoreStackingError):
                trainer._finish_episode()

        self.assertEqual(trainer.episode, episode_before)
        self.assertEqual(trainer.baseline, baseline_before)
        self.assertEqual(trainer.score_history, history_before)
        self.assertIs(trainer.dictionary, dictionary_before)
        self.assertEqual(
            [environment.placements for environment in trainer.environments],
            placements_before,
        )

    def test_episode_done_separates_completed_and_next_dictionaries(self) -> None:
        trainer = self._trainer(3)
        trainer.step(trainer.generation_id, trainer.episode)
        completed_dictionary = [
            server._public_module(module) for module in trainer.dictionary
        ]

        event = trainer._finish_episode()

        self.assertEqual(event["dictionary"], completed_dictionary)
        self.assertEqual(
            event["nextDictionary"],
            [server._public_module(module) for module in trainer.dictionary],
        )
        completed_ids = {module["id"] for module in event["dictionary"]}
        self.assertTrue(
            all(item["module"]["id"] in completed_ids for item in event["placements"])
        )

    def test_failed_site_adaptation_retains_prior_generation(self) -> None:
        trainer = self._trainer(3)
        generation_before = trainer.generation_id
        environments_before = trainer.environments

        with mock.patch.object(
            G,
            "adapt_boundaries_for_core_reserve",
            side_effect=ValueError("forced no common reserve"),
        ):
            with self.assertRaises(server.CoreStackingError):
                trainer.new_site()

        self.assertEqual(trainer.generation_id, generation_before)
        self.assertIs(trainer.environments, environments_before)
        self.assertEqual(trainer.site_event()["stacking"]["status"], "ready")

    def test_settings_and_new_site_publish_deterministic_legal_reserves(self) -> None:
        def run_sequence() -> list[dict]:
            torch.manual_seed(4102)
            trainer = self._trainer(4, "ushape", "central")
            def capture(event: dict) -> dict:
                self.assertEqual(event["stacking"]["status"], "ready")
                self.assertGreater(event["stacking"]["initialCandidateCount"], 0)
                reserve = event["stacking"]["reserve"]
                for environment in trainer.environments:
                    self.assertTrue(
                        G.polygon_inside_site(
                            reserve,
                            environment.site["outer"],
                            environment.site["holes"],
                        )
                    )
                return {
                    "boundaries": event["boundaries"],
                    "stacking": event["stacking"],
                }

            first = capture(trainer.site_event())
            second = capture(trainer.new_site())
            return [first, second]

        self.assertEqual(run_sequence(), run_sequence())

    def test_every_boundary_family_exposes_a_legal_first_stack(self) -> None:
        for boundary_type in sorted(server.BOUNDARY_TYPES):
            with self.subTest(boundary_type=boundary_type):
                trainer = self._trainer(3, boundary_type, "central")
                event = trainer.step(trainer.generation_id, trainer.episode)
                self.assertEqual(len(event["placements"]), 3)
                self.assertTrue(event["stacking"]["exactLocalAlignment"])
                self.assertTrue(
                    all(
                        G.polygon_inside_site(
                            environment.placements[0]["poly"],
                            environment.site["outer"],
                            environment.site["holes"],
                        )
                        for environment in trainer.environments
                    )
                )


if __name__ == "__main__":
    unittest.main()
