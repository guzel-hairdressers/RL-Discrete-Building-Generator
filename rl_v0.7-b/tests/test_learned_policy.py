"""Learned vector dictionary, site encoding, and atrium-policy regressions."""

from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

import torch


MODULE_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

import geometry as G  # noqa: E402
import server  # noqa: E402


class LearnedPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        torch.manual_seed(2468)

    @staticmethod
    def _environment(index: int, width: float, height: float) -> server.FloorEnvironment:
        boundary = G.make_boundary(
            "rect",
            100 + index,
            {"boundaryWidth": width, "boundaryHeight": height},
        )
        site = G.build_site(boundary, [])
        return server.FloorEnvironment(
            index,
            boundary,
            {"id": "none", "label": "No atrium", "holes": []},
            site,
            (0.0, 0.0),
            G.RNG(200 + index),
        )

    @staticmethod
    def _atrium_candidates(boundary: dict) -> list[dict]:
        bounds = G.bounds_of(boundary["outer"])
        width = bounds["maxX"] - bounds["minX"]
        height = bounds["maxY"] - bounds["minY"]
        center_x = (bounds["minX"] + bounds["maxX"]) / 2.0
        center_y = (bounds["minY"] + bounds["maxY"]) / 2.0
        centered = [
            {"x": center_x - 1.0, "y": center_y - 1.0},
            {"x": center_x + 1.0, "y": center_y - 1.0},
            {"x": center_x + 1.0, "y": center_y + 1.0},
            {"x": center_x - 1.0, "y": center_y + 1.0},
        ]
        far_x = bounds["minX"] + width * 0.22
        far_y = bounds["minY"] + height * 0.22
        off_center = [
            {"x": far_x - 2.0, "y": far_y - 2.0},
            {"x": far_x + 2.0, "y": far_y - 2.0},
            {"x": far_x + 2.0, "y": far_y + 2.0},
            {"x": far_x - 2.0, "y": far_y + 2.0},
        ]
        return [
            {"id": "none", "label": "No atrium", "holes": []},
            {
                "id": "centered",
                "label": "Centered court",
                "holes": [centered],
                "area": G.polygon_area(centered),
            },
            {
                "id": "larger-off-center",
                "label": "Larger off-center court",
                "holes": [off_center],
                "area": G.polygon_area(off_center),
            },
        ]

    @staticmethod
    def _head_state(head: torch.nn.Module) -> list[torch.Tensor]:
        return [parameter.detach().clone() for parameter in head.parameters()]

    @staticmethod
    def _head_changed(before: list[torch.Tensor], head: torch.nn.Module) -> bool:
        return any(
            not torch.equal(previous, current.detach())
            for previous, current in zip(before, head.parameters())
        )

    def test_dictionary_is_synthesized_from_learned_latent_actions(self) -> None:
        trainer = server.ParallelTrainer()
        trainer.update_settings(
            {
                "boundaryType": "rect",
                "atriumPolicy": "none",
                "parallelEnvironments": 1,
                "maxModules": 10,
                "dictCap": 6,
                "angleStep": 90.0,
                "seed": 1701,
            }
        )

        self.assertEqual(len(trainer.dictionary), 6)
        self.assertEqual(
            {"core", "room"},
            {module["category"] for module in trainer.dictionary},
        )
        for module in trainer.dictionary:
            with self.subTest(module=module["id"]):
                self.assertTrue(module.get("learnedGeometry"))
                self.assertTrue(module["parameters"].get("learnedGeometry"))
                latent = module["parameters"]["latent"]["input"]
                self.assertEqual(len(latent), server.LATENT_ACTION_DIM)
                self.assertTrue(all(0.0 <= value <= 1.0 for value in latent))

        expected_policy_actions = (6 - 2) + 6
        self.assertEqual(len(trainer.shape_log_probs), expected_policy_actions)
        self.assertTrue(all(log_prob.requires_grad for log_prob in trainer.shape_log_probs))

    @unittest.skip("Legacy latent geometry test removed in v0.5")
    def test_rejected_geometry_proposals_remain_in_slot_policy_term(self) -> None:
        trainer = server.ParallelTrainer()
        settings = server.validate_settings_patch(
            server.DEFAULT_SETTINGS,
            {
                "boundaryType": "rect",
                "atriumPolicy": "none",
                "parallelEnvironments": 1,
                "maxModules": 10,
                "dictCap": 3,
                "angleStep": 90.0,
                "seed": 1703,
            },
        )
        environments = [self._environment(0, 40.0, 30.0)]
        proposal_terms: list[torch.Tensor] = []
        terms_by_action: dict[int, torch.Tensor] = {}

        class RecordingGeometryDistribution:
            def __init__(self, *_args: object, **_kwargs: object) -> None:
                pass

            def sample(self) -> torch.Tensor:
                action = torch.zeros(
                    server.LATENT_ACTION_DIM,
                    dtype=torch.float32,
                    device=trainer.device,
                )
                term = torch.tensor(
                    float(len(proposal_terms) + 1),
                    dtype=torch.float32,
                    device=trainer.device,
                    requires_grad=True,
                )
                proposal_terms.append(term)
                terms_by_action[id(action)] = term
                return action

            def log_prob(self, action: torch.Tensor) -> torch.Tensor:
                return terms_by_action[id(action)]

        actual_synthesize = G.synthesize_module_from_latent
        synthesize_calls = 0

        def reject_once_then_synthesize(
            active_settings: dict,
            category: str,
            latent: list[float],
            identifier: str,
        ) -> dict:
            nonlocal synthesize_calls
            synthesize_calls += 1
            if synthesize_calls == 1:
                raise ValueError("forced first-proposal rejection")
            return actual_synthesize(active_settings, category, latent, identifier)

        with (
            mock.patch.object(
                torch.distributions,
                "Independent",
                side_effect=RecordingGeometryDistribution,
            ),
            mock.patch.object(
                G,
                "synthesize_module_from_latent",
                side_effect=reject_once_then_synthesize,
            ),
        ):
            dictionary, slot_policy_terms = trainer._synthesize_dictionary(
                settings,
                environments,
                generation_id=4,
                episode=2,
            )

        self.assertEqual(len(dictionary), 3)
        self.assertEqual(synthesize_calls, 4)
        self.assertEqual(len(proposal_terms), 4)
        self.assertEqual(len(slot_policy_terms), 3)
        self.assertAlmostEqual(
            float(slot_policy_terms[0].detach().cpu()),
            float((proposal_terms[0] + proposal_terms[1]).detach().cpu()),
            places=7,
        )
        rejected_gradient, accepted_gradient = torch.autograd.grad(
            slot_policy_terms[0],
            (proposal_terms[0], proposal_terms[1]),
            allow_unused=True,
        )
        self.assertIsNotNone(rejected_gradient)
        self.assertIsNotNone(accepted_gradient)
        self.assertEqual(float(rejected_gradient.detach().cpu()), 1.0)
        self.assertEqual(float(accepted_gradient.detach().cpu()), 1.0)

    def test_floor_descriptors_preserve_shape_and_affect_learned_pooling(self) -> None:
        trainer = server.ParallelTrainer()
        settings = server.validate_settings_patch(
            server.DEFAULT_SETTINGS,
            {"parallelEnvironments": 2, "maxModules": 10},
        )
        environments = [
            self._environment(0, 40.0, 24.0),
            self._environment(1, 30.0, 32.0),
        ]

        descriptors = trainer._site_descriptor(environments, settings)
        descriptor_tensor = torch.tensor(descriptors, dtype=torch.float32, device=trainer.device)
        self.assertEqual(tuple(descriptor_tensor.shape), (2, server.FLOOR_DESCRIPTOR_DIM))
        self.assertAlmostEqual(descriptors[0][0], descriptors[1][0], places=7)
        self.assertNotEqual(descriptors[0][3:5], descriptors[1][3:5])
        self.assertNotEqual(descriptors[0], descriptors[1])

        repeated = torch.tensor(
            [descriptors[0], descriptors[0]], dtype=torch.float32, device=trainer.device
        )
        repeated_pool = trainer.model.encode_sites(repeated)
        mixed_pool = trainer.model.encode_sites(descriptor_tensor)
        self.assertEqual(tuple(mixed_pool.shape), (server.POOLED_SITE_DIM,))
        self.assertFalse(torch.allclose(repeated_pool, mixed_pool, atol=1.0e-7, rtol=1.0e-7))

    def test_central_atrium_is_closest_to_boundary_centroid_not_largest(self) -> None:
        trainer = server.ParallelTrainer()
        settings = server.validate_settings_patch(
            server.DEFAULT_SETTINGS,
            {"atriumPolicy": "central"},
        )
        boundary = G.make_boundary(
            "rect",
            77,
            {"boundaryWidth": 40.0, "boundaryHeight": 30.0},
        )
        candidates = self._atrium_candidates(boundary)

        choice, log_prob = trainer._choose_atrium(settings, boundary, candidates)

        self.assertEqual(choice["id"], "centered")
        self.assertLess(choice["area"], candidates[2]["area"])
        self.assertIsNone(log_prob)

    @unittest.skip("Legacy latent geometry test removed in v0.5")
    def test_episode_backprop_reaches_geometry_and_agent_atrium_heads(self) -> None:
        trainer = server.ParallelTrainer()
        with mock.patch.object(
            G,
            "atrium_candidates",
            side_effect=lambda boundary, _rng: self._atrium_candidates(boundary),
        ):
            trainer.update_settings(
                {
                    "boundaryType": "rect",
                    "atriumPolicy": "agent",
                    "parallelEnvironments": 1,
                    "maxModules": 10,
                    "dictCap": 6,
                    "angleStep": 90.0,
                    "seed": 1702,
                }
            )

        expected_shape_and_atrium_actions = 1 + 6 + (6 - 3)
        self.assertEqual(len(trainer.shape_log_probs), expected_shape_and_atrium_actions)
        self.assertTrue(all(log_prob.requires_grad for log_prob in trainer.shape_log_probs))
        geometry_before = self._head_state(trainer.model.geometry_head)
        atrium_before = self._head_state(trainer.model.atrium_head)

        for environment in trainer.environments:
            environment.done = True
        event = trainer.step(trainer.generation_id, trainer.episode)

        self.assertEqual(event["type"], "episodeDone")
        self.assertNotEqual(event["metrics"]["policyLoss"], 0.0)
        self.assertTrue(self._head_changed(geometry_before, trainer.model.geometry_head))
        self.assertTrue(self._head_changed(atrium_before, trainer.model.atrium_head))


if __name__ == "__main__":
    unittest.main()
