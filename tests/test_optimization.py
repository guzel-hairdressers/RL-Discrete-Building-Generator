"""Regression tests for the v0.8.1 optimization and learner contracts."""

from __future__ import annotations

import copy
import io
import math
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

import torch


MODULE_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR / "src"))
sys.path.insert(0, str(MODULE_DIR))

import geometry as G  # noqa: E402
import server  # noqa: E402


class LearnerOptimizationTests(unittest.TestCase):
    def setUp(self) -> None:
        checkpoint_gate = mock.patch.object(
            server, "_safe_checkpoint_loading_supported", return_value=True
        )
        checkpoint_gate.start()
        self.addCleanup(checkpoint_gate.stop)

    def test_device_override_supports_cpu_and_individual_cuda_workers(self) -> None:
        with mock.patch.dict(server.os.environ, {"MODULE_LAB_DEVICE": "cpu"}), mock.patch.object(
            torch.cuda, "is_available", return_value=True
        ):
            self.assertEqual(str(server.select_device()), "cpu")
        with mock.patch.dict(
            server.os.environ, {"MODULE_LAB_DEVICE": "cuda:1"}
        ), mock.patch.object(torch.cuda, "is_available", return_value=True), mock.patch.object(
            torch.cuda, "device_count", return_value=2
        ):
            self.assertEqual(str(server.select_device()), "cuda:1")
        with mock.patch.dict(
            server.os.environ, {"MODULE_LAB_DEVICE": "cuda:2"}
        ), mock.patch.object(torch.cuda, "is_available", return_value=True), mock.patch.object(
            torch.cuda, "device_count", return_value=2
        ), self.assertRaises(RuntimeError):
            server.select_device()

    def test_trajectory_aggregation_does_not_overweight_short_rollouts(self) -> None:
        grouped = {
            0: [torch.tensor(-1.0), torch.tensor(-1.0)],
            1: [torch.tensor(-3.0)],
        }
        result = server._mean_trajectory_log_probability(grouped)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(float(result), -2.5)
        self.assertNotAlmostEqual(float(result), -5.0 / 3.0)

    def test_empty_terminal_episode_trains_finite_critic(self) -> None:
        trainer = server.ParallelTrainer()
        trainer.settings["dictCap"] = 1
        event = trainer._finish_episode()
        metrics = event["metrics"]
        self.assertEqual(metrics["learningAlgorithm"], "monte_carlo_actor_critic")
        for key in ("policyLoss", "actorLoss", "valueLoss", "gradientNorm", "advantage"):
            self.assertTrue(math.isfinite(float(metrics[key])), key)
        self.assertGreaterEqual(metrics["valueLoss"], 0.0)

    def test_v3_checkpoint_without_critic_loads_with_fresh_optimizer_state(self) -> None:
        trainer = server.ParallelTrainer()
        model_state = {
            name: tensor.detach().cpu()
            for name, tensor in trainer.model.state_dict().items()
            if not name.startswith("value_head.")
        }
        optimizer_state = copy.deepcopy(trainer.optimizer.state_dict())
        optimizer_state["param_groups"][0]["params"] = optimizer_state["param_groups"][0][
            "params"
        ][:-4]
        for parameter in trainer.model.value_head.parameters():
            parameter.data.fill_(42.0)
        legacy_settings = dict(trainer.settings)
        legacy_settings.update({"learningRate": 0.1, "maxEdges": 4, "maxEdge": 4.5})
        payload = io.BytesIO()
        torch.save(
            {
                "version": 3,
                "model": model_state,
                "optimizer": optimizer_state,
                "settings": legacy_settings,
                "generationId": 2,
                "episode": 3,
            },
            payload,
        )
        event = trainer.load_checkpoint_data(payload.getvalue())
        self.assertEqual(event["type"], "site")
        self.assertEqual(trainer.generation_id, 3)
        self.assertEqual(trainer.episode, 3)
        self.assertEqual(trainer.settings["learningRate"], 0.05)
        self.assertEqual(trainer.settings["maxEdge"], 5.0)
        self.assertTrue(all(torch.isfinite(p).all() for p in trainer.model.parameters()))
        self.assertTrue(
            all(not torch.all(parameter == 42.0) for parameter in trainer.model.value_head.parameters())
        )

    def test_v5_checkpoint_restores_reward_references_and_rng(self) -> None:
        source = server.ParallelTrainer()
        source.generation_time_history.extend([1.25, 2.5])
        source.frontier_growth_history.extend([3.0, 4.0])
        source.generation_time_baseline = 1.75
        source.frontier_growth_baseline = 3.5
        source.baseline_transition_remaining = 2
        source.baseline_transition_anchor_reward = 0.4
        source.last_frontier_reward = 0.6
        source.reward_settings_signature = (
            source._reward_signature(source.settings),
            source._reward_site_fingerprint(source.environments),
            source._reward_dictionary_fingerprint(source.dictionary),
        )
        expected_rng = torch.random.get_rng_state().clone()

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            server, "OUTPUT_DIR", directory
        ):
            payload = pathlib.Path(source.save_checkpoint()).read_bytes()

        target = server.ParallelTrainer()
        target.generation_time_history.extend([99.0])
        target.frontier_growth_history.extend([99.0])
        torch.manual_seed(999999)
        prepared = (target.environments, target.dictionary, [])
        with mock.patch.object(target, "_prepare_generation", return_value=prepared):
            target.load_checkpoint_data(payload)

        self.assertEqual(tuple(target.generation_time_history), (1.25, 2.5))
        self.assertEqual(tuple(target.frontier_growth_history), (3.0, 4.0))
        self.assertEqual(target.generation_time_baseline, 1.75)
        self.assertEqual(target.frontier_growth_baseline, 3.5)
        self.assertEqual(target.baseline_transition_remaining, 2)
        self.assertEqual(target.baseline_transition_anchor_reward, 0.4)
        self.assertEqual(target.last_frontier_reward, 0.6)
        self.assertTrue(torch.equal(torch.random.get_rng_state(), expected_rng))

    def test_checkpoint_loader_rejects_non_torch_pickle_data(self) -> None:
        trainer = server.ParallelTrainer()
        with self.assertRaises(Exception):
            trainer.load_checkpoint_data(b"not a safe torch checkpoint")

    def test_vulnerable_torch_versions_fail_closed_before_deserialization(self) -> None:
        trainer = server.ParallelTrainer()
        with mock.patch.object(
            server, "_safe_checkpoint_loading_supported", return_value=False
        ), mock.patch.object(server.torch, "load") as torch_load, self.assertRaisesRegex(
            RuntimeError, "CVE-2025-32434"
        ):
            trainer.load_checkpoint_data(b"untrusted checkpoint bytes")
        torch_load.assert_not_called()

    def test_malformed_v5_checkpoint_is_rejected_atomically(self) -> None:
        source = server.ParallelTrainer()
        first_parameter = next(source.model.parameters())
        first_parameter.grad = torch.zeros_like(first_parameter)
        source.optimizer.step()
        source.optimizer.zero_grad(set_to_none=True)
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            server, "OUTPUT_DIR", directory
        ):
            checkpoint = torch.load(
                source.save_checkpoint(), map_location="cpu", weights_only=True
            )

        target = server.ParallelTrainer()
        target.update_settings({"boundaryType": "rect", "atriumPolicy": "none", "seed": 918})
        original_generation = target.generation_id
        original_best_score = target.best_score
        original_environments = target.environments
        original_model = {
            name: value.detach().clone() for name, value in target.model.state_dict().items()
        }

        for corruption in (
            "scalar",
            "tensor",
            "optimizer_shape",
            "optimizer_missing",
            "optimizer_group",
            "optimizer_step_bool",
            "optimizer_weight_decay_bool",
            "optimizer_capturable",
            "optimizer_zero_eps",
        ):
            malformed = copy.deepcopy(checkpoint)
            if corruption == "scalar":
                malformed["bestScore"] = "not-a-number"
            elif corruption == "tensor":
                first_name = next(iter(malformed["model"]))
                malformed["model"][first_name].reshape(-1)[0] = float("nan")
            elif corruption == "optimizer_shape":
                first_state = next(iter(malformed["optimizer"]["state"].values()))
                first_state["exp_avg"] = torch.zeros(1)
                first_state["exp_avg_sq"] = torch.zeros(1)
            elif corruption == "optimizer_missing":
                first_state = next(iter(malformed["optimizer"]["state"].values()))
                del first_state["exp_avg"]
            elif corruption == "optimizer_group":
                malformed["optimizer"]["param_groups"][0]["betas"] = "bad"
            elif corruption == "optimizer_step_bool":
                first_state = next(iter(malformed["optimizer"]["state"].values()))
                first_state["step"] = torch.tensor(True)
            elif corruption == "optimizer_weight_decay_bool":
                malformed["optimizer"]["param_groups"][0]["weight_decay"] = True
            elif corruption == "optimizer_capturable":
                malformed["optimizer"]["param_groups"][0]["capturable"] = True
            else:
                malformed["optimizer"]["param_groups"][0]["eps"] = 0.0
            payload = io.BytesIO()
            torch.save(malformed, payload)
            with self.subTest(corruption=corruption), self.assertRaises(ValueError):
                target.load_checkpoint_data(payload.getvalue())
            self.assertEqual(target.generation_id, original_generation)
            self.assertEqual(target.best_score, original_best_score)
            self.assertIs(target.environments, original_environments)
            for name, value in target.model.state_dict().items():
                self.assertTrue(torch.equal(value, original_model[name]), name)

    def test_checkpoint_save_replaces_atomically_and_cleans_failed_temporary(self) -> None:
        trainer = server.ParallelTrainer()
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            server, "OUTPUT_DIR", directory
        ):
            checkpoint_path = pathlib.Path(trainer.save_checkpoint())
            original = checkpoint_path.read_bytes()
            self.assertTrue(original)
            self.assertEqual(list(checkpoint_path.parent.glob("*.tmp")), [])

            def fail_after_partial_write(_payload, temporary_path) -> None:
                pathlib.Path(temporary_path).write_bytes(b"partial")
                raise RuntimeError("simulated checkpoint write failure")

            with mock.patch.object(
                server.torch, "save", side_effect=fail_after_partial_write
            ), self.assertRaisesRegex(RuntimeError, "simulated checkpoint write failure"):
                trainer.save_checkpoint()

            self.assertEqual(checkpoint_path.read_bytes(), original)
            self.assertEqual(list(checkpoint_path.parent.glob("*.tmp")), [])

            with mock.patch.object(
                server.os, "replace", side_effect=RuntimeError("simulated replace failure")
            ), self.assertRaisesRegex(RuntimeError, "simulated replace failure"):
                trainer.save_checkpoint()

            self.assertEqual(checkpoint_path.read_bytes(), original)
            self.assertEqual(list(checkpoint_path.parent.glob("*.tmp")), [])

    def test_browser_websocket_origins_are_local_only(self) -> None:
        self.assertTrue(server._allowed_websocket_origin(None))
        self.assertTrue(server._allowed_websocket_origin("http://127.0.0.1:8000"))
        self.assertTrue(server._allowed_websocket_origin("http://localhost:8000"))
        self.assertFalse(server._allowed_websocket_origin("https://attacker.example"))


class RuntimeOptimizationTests(unittest.TestCase):
    def make_trainer(self) -> server.ParallelTrainer:
        trainer = server.ParallelTrainer()
        trainer.update_settings(
            {
                "boundaryType": "rect",
                "atriumPolicy": "none",
                "parallelEnvironments": 1,
                "maxModules": 10,
                "dictCap": 6,
                "angleStep": 90.0,
                "seed": 812,
            }
        )
        return trainer

    def test_single_category_initial_search_stops_at_bounded_quota(self) -> None:
        trainer = self.make_trainer()
        rectangle = G._module_record(
            identifier="quota-probe",
            name="Quota Probe",
            category="shape",
            poly=[
                {"x": 0.0, "y": 0.0},
                {"x": 6.0, "y": 0.0},
                {"x": 6.0, "y": 4.0},
                {"x": 0.0, "y": 4.0},
            ],
            family="test",
            edge_range_compatible=True,
            source_parameters={"generator": "test"},
        )
        module = trainer._canonical_module(rectangle, 90.0, phase=0)
        environment = trainer.environments[0]
        environment.reset([module])
        candidates = environment.generate_candidates(trainer.settings, limit=12)
        geometric_candidates = [
            candidate for candidate in candidates if candidate.module["id"] == module["id"]
        ]
        self.assertEqual(len(geometric_candidates), 12)
        self.assertLessEqual(environment.last_candidate_evaluations, 128)

    def test_three_edge_cap_masks_quads_and_fallback_keeps_trace_probability(self) -> None:
        trainer = server.ParallelTrainer()
        settings = server.validate_settings_patch(
            trainer.settings,
            {
                "maxEdges": 3,
                "maxEdge": 9.0,
                "angleStep": 90.0,
                "parallelEnvironments": 1,
            },
        )
        environments, _ = trainer._build_sites(settings, generation_id=1)
        with mock.patch.object(
            G, "synthesize_custom_module", side_effect=ValueError("force fallback")
        ):
            module, trace_log_probability = trainer._sample_custom_shape(
                settings, environments, slot_index=0
            )
        self.assertEqual(len(module["poly"]), 3)
        self.assertTrue(torch.isfinite(trace_log_probability))
        self.assertLess(float(trace_log_probability.detach()), -0.1)

        integrated = server.ParallelTrainer()
        integrated.update_settings(
            {
                "maxEdges": 3,
                "maxEdge": 9.0,
                "angleStep": 90.0,
                "parallelEnvironments": 1,
                "atriumPolicy": "none",
                "seed": 3303,
            }
        )
        integrated.step(integrated.generation_id, integrated.episode)
        self.assertTrue(integrated.dictionary)
        self.assertTrue(all(len(item["poly"]) <= 3 for item in integrated.dictionary))
        self.assertTrue(
            all(
                len(placement["poly"]) <= 3
                for environment in integrated.environments
                for placement in environment.placements
            )
        )

        quad_only_settings = server.validate_settings_patch(
            trainer.settings,
            {
                "maxEdges": 4,
                "maxEdge": 5.0,
                "angleStep": 90.0,
                "parallelEnvironments": 1,
            },
        )
        quad_environments, _ = trainer._build_sites(quad_only_settings, generation_id=2)
        for seed in range(5):
            torch.manual_seed(seed)
            core_module, _ = trainer._sample_custom_shape(
                quad_only_settings, quad_environments, slot_index=seed
            )
            self.assertEqual(len(core_module["poly"]), 4)
            self.assertGreaterEqual(core_module["area"], 24.0 - 1.0e-8)

    def test_remote_core_fallback_rechecks_strict_edge_alignment(self) -> None:
        trainer = self.make_trainer()
        module_record = G._module_record(
            identifier="remote-core-probe",
            name="Remote Core Probe",
            category="shape",
            poly=[
                {"x": 0.0, "y": 0.0},
                {"x": 6.0, "y": 0.0},
                {"x": 6.0, "y": 4.0},
                {"x": 0.0, "y": 4.0},
            ],
            family="test",
            edge_range_compatible=True,
            source_parameters={"generator": "test"},
        )
        module = trainer._canonical_module(module_record, 90.0, phase=0)
        environment = trainer.environments[0]
        environment.reset([module])
        environment.placements = [
            {"id": f"room-{index}", "category": "room"}
            for index in range(server.SECOND_CORE_MIN_ROOMS)
        ]
        candidate = server.PlacementCandidate(
            module={**module, "category": "core"},
            rotation=module["rotations"][0],
            poly=[dict(point) for point in module["poly"]],
            cells=[],
            neighbors=["room-0"],
            shared_overlap=1.0,
            outer_exposure=0.0,
            features=[0.0] * server.PLACEMENT_FEATURE_DIM,
        )
        with mock.patch.object(
            environment, "_edge_alignment_anchors", return_value=[]
        ), mock.patch.object(
            environment, "_candidate_from_anchor", return_value=candidate
        ), mock.patch.object(
            environment, "_validate_edge_alignment", return_value=False
        ) as validate_alignment, mock.patch.object(
            environment, "_materialize_candidate"
        ) as materialize:
            candidates = environment.generate_candidates(trainer.settings, limit=12)
        self.assertGreater(validate_alignment.call_count, 0)
        materialize.assert_not_called()
        self.assertFalse(
            any(candidate.module.get("category") == "core" for candidate in candidates)
        )

    def test_attachment_cap_rotates_a_stratified_frontier_view(self) -> None:
        trainer = self.make_trainer()
        environment = trainer.environments[0]
        identifiers = list(range(40))
        observed: set[int] = set()
        for _ in range(40):
            sample = environment._sample_attachment_ids(identifiers)
            self.assertEqual(len(sample), server.ATTACHMENT_MATCH_LIMIT)
            observed.update(sample)
        self.assertEqual(observed, set(identifiers))

    def test_failed_shape_proposal_retries_before_ending_floor(self) -> None:
        trainer = self.make_trainer()
        environment = trainer.environments[0]
        with mock.patch.object(
            trainer, "_sample_custom_shape", side_effect=ValueError("invalid shape")
        ):
            event = trainer.step(trainer.generation_id, trainer.episode)
        self.assertEqual(event["type"], "placements")
        self.assertFalse(environment.done)
        self.assertEqual(environment.consecutive_proposal_failures, 1)

    def test_future_shape_capacity_preserves_currently_unmatched_ports(self) -> None:
        trainer = self.make_trainer()
        trainer.step(trainer.generation_id, trainer.episode)
        environment = trainer.environments[0]
        attachment_ids = set(environment.attachment_edges)
        self.assertTrue(attachment_ids)
        with mock.patch.object(environment, "_candidate_from_anchor", return_value=None):
            candidates = environment.generate_candidates(trainer.settings, limit=12)
        self.assertEqual(set(environment.attachment_edges), attachment_ids)
        self.assertTrue(
            any(candidate.module.get("id") == "create_new" for candidate in candidates)
        )

    def test_frontier_compatible_repair_can_attach_to_initial_core(self) -> None:
        trainer = self.make_trainer()
        trainer.step(trainer.generation_id, trainer.episode)
        environment = trainer.environments[0]
        modules = trainer._frontier_compatible_modules(
            trainer.settings, environment, len(trainer.dictionary)
        )
        self.assertTrue(modules)
        self.assertTrue(all(module["area"] >= 8.0 - 1.0e-8 for module in modules))
        self.assertTrue(
            any(
                environment.generate_candidates_for_module(
                    module, trainer.settings, 0.0, limit=12
                )
                for module in modules
            )
        )

    def test_optional_second_core_is_delayed_until_room_frontier_exists(self) -> None:
        trainer = self.make_trainer()
        trainer.step(trainer.generation_id, trainer.episode)
        environment = trainer.environments[0]
        candidates = environment.generate_candidates(trainer.settings, limit=12)
        self.assertFalse(
            any(candidate.module.get("category") == "core" for candidate in candidates)
        )

    def test_undersized_shape_is_never_offered_as_a_core(self) -> None:
        trainer = self.make_trainer()
        small = G._module_record(
            identifier="small-core-probe",
            name="Small Core Probe",
            category="shape",
            poly=[
                {"x": 0.0, "y": 0.0},
                {"x": 3.0, "y": 0.0},
                {"x": 3.0, "y": 3.0},
                {"x": 0.0, "y": 3.0},
            ],
            family="test",
            edge_range_compatible=True,
            source_parameters={"generator": "test"},
        )
        module = trainer._canonical_module(small, 90.0, phase=0)
        environment = trainer.environments[0]
        environment.reset([module])
        candidates = environment.generate_candidates(trainer.settings, limit=12)
        self.assertFalse(
            any(candidate.module.get("category") == "core" for candidate in candidates)
        )

    def test_intermediate_step_defers_full_bpe(self) -> None:
        trainer = self.make_trainer()
        event = trainer.step(trainer.generation_id, trainer.episode)
        self.assertEqual(event["type"], "placements")
        self.assertEqual(event["mergedPlacements"], [])
        self.assertEqual(event["mergedDictionary"], [])
        self.assertEqual(event["metrics"]["performanceTimings"]["bpeMerge"]["avg"], 0.0)

    def test_evaluation_is_repeatable_and_does_not_advance_reward_state(self) -> None:
        trainer = self.make_trainer()
        trainer.step(trainer.generation_id, trainer.episode)
        state_before = (
            trainer.topology_multiplier,
            tuple(trainer.generation_time_history),
            tuple(trainer.frontier_growth_history),
            trainer.generation_time_baseline,
            trainer.frontier_growth_baseline,
            trainer.baseline_transition_remaining,
        )
        first = trainer.evaluate(trainer.generation_id, trainer.episode)
        second = trainer.evaluate(trainer.generation_id, trainer.episode)
        self.assertEqual(first["metrics"]["score"], second["metrics"]["score"])
        self.assertEqual(
            first["metrics"]["topologyMultiplier"],
            second["metrics"]["topologyMultiplier"],
        )
        self.assertEqual(
            state_before,
            (
                trainer.topology_multiplier,
                tuple(trainer.generation_time_history),
                tuple(trainer.frontier_growth_history),
                trainer.generation_time_baseline,
                trainer.frontier_growth_baseline,
                trainer.baseline_transition_remaining,
            ),
        )

    def test_hardware_time_is_telemetry_not_reward(self) -> None:
        trainer = self.make_trainer()
        trainer.generation_time_baseline = 1.0
        trainer.frontier_growth_baseline = 2.0
        trainer.episode_frontier_growth = 3.0
        trainer.episode_frontier_samples = 1
        trainer.episode_action_normalized_seconds = 1.0
        fast = trainer._relative_frontier_reward(update_state=False)
        trainer.episode_action_normalized_seconds = 100.0
        slow = trainer._relative_frontier_reward(update_state=False)
        self.assertNotEqual(
            fast["relativeGenerationTime"], slow["relativeGenerationTime"]
        )
        self.assertEqual(fast["relativeTimeReward"], slow["relativeTimeReward"])

    def test_runtime_diagnostics_expose_native_and_memory_status(self) -> None:
        trainer = self.make_trainer()
        event = trainer.site_event()
        diagnostics = event["diagnostics"]
        self.assertEqual(diagnostics, event["metrics"]["runtimeDiagnostics"])
        self.assertIn("nativeGeometry", diagnostics)
        self.assertIn("enabled", diagnostics["nativeGeometry"])
        self.assertGreaterEqual(diagnostics["processPeakRssBytes"], 0)
        self.assertGreaterEqual(diagnostics["torchThreads"], 1)


if __name__ == "__main__":
    unittest.main()
