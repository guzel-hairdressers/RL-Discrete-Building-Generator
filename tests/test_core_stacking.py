"""Exact cross-floor core transactions introduced for v0.8.0."""

from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

import torch


MODULE_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR / "src"))
sys.path.insert(0, str(MODULE_DIR))

import server  # noqa: E402


class CoreStackingTests(unittest.TestCase):
    def setUp(self) -> None:
        torch.manual_seed(8080)

    @staticmethod
    def make_trainer(floor_count: int = 4, **patch: object) -> server.ParallelTrainer:
        trainer = server.ParallelTrainer()
        settings = {
            "boundaryType": "lobed",
            "atriumPolicy": "none",
            "parallelEnvironments": floor_count,
            "maxModules": 10,
            "dictCap": 6,
            "angleStep": 90.0,
            "seed": 808,
        }
        settings.update(patch)
        trainer.update_settings(settings)
        return trainer

    def test_first_action_is_one_exact_building_action_on_four_and_eight_floors(self) -> None:
        for floor_count in (4, 8):
            with self.subTest(floor_count=floor_count):
                torch.manual_seed(8080 + floor_count)
                trainer = self.make_trainer(floor_count)
                site_event = trainer.site_event()
                self.assertTrue(site_event["coreStacking"]["enabled"])
                self.assertGreater(
                    site_event["coreStacking"]["initialCandidateCount"], 0
                )

                event = trainer.step(trainer.generation_id, trainer.episode)
                self.assertEqual(len(event["placements"]), floor_count)
                self.assertEqual(len(trainer.placement_log_probs), 1)
                self.assertEqual(len(trainer.placement_decisions), 1)
                self.assertEqual(len(trainer.building_shape_log_probs), 1)
                self.assertIn(
                    trainer.building_shape_log_probs[0],
                    trainer.shape_log_probs,
                )
                self.assertEqual(
                    trainer.placement_decisions[0].environment_index,
                    server.BUILDING_TRAJECTORY_INDEX,
                )
                self.assertEqual(len(trainer.core_stack_records), 1)
                self.assertEqual(
                    trainer.core_stack_records[0]["decisionScope"], "building"
                )
                self.assertEqual(trainer.core_stack_records[0]["logProbTerms"], 1)

                placements = [environment.placements[0] for environment in trainer.environments]
                reference = placements[0]
                for placement in placements:
                    self.assertEqual(placement["category"], "core")
                    self.assertTrue(placement["coreStackLocked"])
                    self.assertEqual(placement["moduleId"], reference["moduleId"])
                    self.assertEqual(placement["rotation"], reference["rotation"])
                    self.assertEqual(placement["localAnchor"], reference["localAnchor"])
                    self.assertEqual(placement["poly"], reference["poly"])

                audit = event["coreStacking"]
                self.assertTrue(audit["exactLocalAlignment"])
                self.assertEqual(audit["lockedCoreCount"], floor_count)
                self.assertEqual(audit["violations"], [])

    def test_optional_second_stack_waits_for_six_rooms_on_every_floor(self) -> None:
        trainer = self.make_trainer(4, boundaryType="rect", seed=83)
        trainer.step(trainer.generation_id, trainer.episode)

        self.assertTrue(all(len(environment.core_ids) == 1 for environment in trainer.environments))
        self.assertEqual(trainer._shared_core_stack_candidates(0.0), [])

        # Advancing only one floor cannot force a building-level core action
        # onto peers whose room frontier has not matured.
        source = trainer.environments[0].placements[0]
        for index in range(server.SECOND_CORE_MIN_ROOMS):
            trainer.environments[0].placements.append(
                {**source, "id": f"synthetic-room-{index}", "category": "room"}
            )
        self.assertEqual(trainer._shared_core_stack_candidates(0.0), [])

    def test_floor_count_can_change_atomically_between_settings_generations(self) -> None:
        trainer = self.make_trainer(4, boundaryType="rect", seed=89)
        generation = trainer.generation_id
        prior_environments = list(trainer.environments)

        event = trainer.update_settings({"parallelEnvironments": 8})

        self.assertEqual(trainer.generation_id, generation + 1)
        self.assertEqual(len(trainer.environments), 8)
        self.assertTrue(event["coreStacking"]["enabled"])
        self.assertGreater(event["coreStacking"]["initialCandidateCount"], 0)
        self.assertTrue(
            all(
                environment not in prior_environments
                for environment in trainer.environments
            )
        )
        placement_event = trainer.step(trainer.generation_id, trainer.episode)
        self.assertEqual(len(placement_event["placements"]), 8)
        self.assertTrue(placement_event["coreStacking"]["exactLocalAlignment"])

    def test_failed_floor_commit_rolls_back_every_targeted_index(self) -> None:
        trainer = self.make_trainer(4, boundaryType="rect", seed=33)
        candidate = trainer._prepared_initial_core_stacks[0]
        before = [
            environment._stack_commit_checkpoint()
            for environment in trainer.environments
        ]

        with mock.patch.object(
            trainer.environments[1], "place", side_effect=RuntimeError("induced")
        ):
            with self.assertRaises(server.CoreStackingError):
                trainer._commit_core_stack(
                    candidate,
                    torch.tensor(0.0, requires_grad=True),
                    orientation_basis=0.0,
                )

        after = [
            environment._stack_commit_checkpoint()
            for environment in trainer.environments
        ]
        self.assertEqual(after, before)
        self.assertEqual(trainer.placement_log_probs, [])
        self.assertEqual(trainer.core_stack_records, [])

    def test_no_common_transform_retries_the_whole_irregular_site_group(self) -> None:
        trainer = server.ParallelTrainer()
        original_build = trainer._build_sites
        original_shared = trainer._shared_core_stack_candidates
        built_groups: list[list[server.FloorEnvironment]] = []
        attempts: list[int] = []
        shared_calls = 0

        def recording_build(settings, generation_id, attempt=0):
            environments, log_probs = original_build(
                settings, generation_id, attempt=attempt
            )
            built_groups.append(environments)
            attempts.append(attempt)
            return environments, log_probs

        def reject_first_group(*args, **kwargs):
            nonlocal shared_calls
            shared_calls += 1
            if shared_calls == 1:
                return []
            return original_shared(*args, **kwargs)

        with mock.patch.object(trainer, "_build_sites", side_effect=recording_build), mock.patch.object(
            trainer,
            "_shared_core_stack_candidates",
            side_effect=reject_first_group,
        ):
            event = trainer.update_settings(
                {
                    "boundaryType": "lobed",
                    "atriumPolicy": "none",
                    "parallelEnvironments": 4,
                    "seed": 144,
                }
            )

        self.assertEqual(attempts[:2], [0, 1])
        self.assertEqual(len(built_groups[0]), 4)
        self.assertEqual(len(built_groups[1]), 4)
        self.assertTrue(
            all(
                first is not second
                for first, second in zip(built_groups[0], built_groups[1])
            )
        )
        self.assertEqual(event["coreStacking"]["siteResampleAttempts"], 1)
        self.assertEqual(event["coreStacking"]["boundaryPolicy"], "whole-site-resample")
        self.assertTrue(
            all(
                environment.boundary.get("type") != "rect"
                for environment in trainer.environments
            )
        )

    def test_exhausted_preflight_does_not_commit_a_partial_generation(self) -> None:
        trainer = self.make_trainer(4, boundaryType="rect", seed=73)
        generation_before = trainer.generation_id
        environments_before = list(trainer.environments)
        dictionary_before = list(trainer.dictionary)

        with mock.patch.object(server, "CORE_SITE_TRANSACTION_ATTEMPTS", 2), mock.patch.object(
            trainer, "_shared_core_stack_candidates", return_value=[]
        ):
            with self.assertRaises(server.CoreStackingError):
                trainer.new_site()

        self.assertEqual(trainer.generation_id, generation_before)
        self.assertEqual(trainer.environments, environments_before)
        self.assertEqual(trainer.dictionary, dictionary_before)

    def test_single_floor_mode_disables_stacking_even_with_parallel_playgrounds(self) -> None:
        trainer = self.make_trainer(
            4,
            singleFloor=True,
            boundaryType="rect",
            seed=19,
        )
        site_metadata = trainer.site_event()["coreStacking"]
        self.assertFalse(site_metadata["enabled"])
        self.assertEqual(site_metadata["status"], "disabled-single-floor")
        self.assertEqual(trainer.dictionary, [])

        event = trainer.step(trainer.generation_id, trainer.episode)
        self.assertEqual(trainer.core_stack_records, [])
        self.assertFalse(event["coreStacking"]["enabled"])
        self.assertTrue(
            all(placement["module"]["category"] != "core" for placement in event["placements"])
        )


if __name__ == "__main__":
    unittest.main()
