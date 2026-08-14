import json
import os
import shutil
import tempfile
import unittest

from src.server import DEFAULT_SETTINGS, ParallelTrainer, record_dataset_trajectory


class TestInferenceMode(unittest.TestCase):
    def setUp(self) -> None:
        self.trainer = ParallelTrainer(DEFAULT_SETTINGS)
        self.trainer.new_site()
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_mode_switch(self) -> None:
        self.assertEqual(self.trainer.mode, "training")
        ack = self.trainer.set_mode("inference")
        self.assertEqual(ack["type"], "ack")
        self.assertEqual(ack["mode"], "inference")
        self.assertEqual(self.trainer.mode, "inference")

        ack_train = self.trainer.set_mode("training")
        self.assertEqual(ack_train["mode"], "training")
        self.assertEqual(self.trainer.mode, "training")

        with self.assertRaises(ValueError):
            self.trainer.set_mode("invalid_mode")

    def test_inference_mode_episode_skips_learning(self) -> None:
        self.trainer.set_mode("inference")
        self.assertEqual(self.trainer.mode, "inference")
        
        # Step until episode completes
        max_steps = 150
        event = None
        for _ in range(max_steps):
            event = self.trainer.step(self.trainer.generation_id, self.trainer.episode)
            if event.get("type") == "episodeDone":
                break

        self.assertIsNotNone(event)
        self.assertEqual(event.get("type"), "episodeDone")
        metrics = event.get("metrics", {})
        self.assertEqual(metrics.get("learningAlgorithm"), "inference_only")
        self.assertEqual(metrics.get("policyLoss"), 0.0)

    def test_record_dataset_trajectory(self) -> None:
        dataset_file = os.path.join(self.test_dir, "test_dataset.jsonl")
        mock_event = {
            "type": "episodeDone",
            "completedEpisode": 1,
            "metrics": {"aggregateReward": 42.5, "fillRatio": 0.85},
            "dictionary": [{"id": "s0", "category": "core"}],
            "mergedDictionary": [],
            "placements": [{"id": "p0", "poly": [{"x": 0, "y": 0}, {"x": 5, "y": 0}, {"x": 5, "y": 5}, {"x": 0, "y": 5}]}],
            "mergedPlacements": [],
        }
        res = record_dataset_trajectory(mock_event, data_dir=self.test_dir, filename="test_dataset.jsonl")
        self.assertIsNotNone(res)
        self.assertTrue(os.path.exists(dataset_file))

        with open(dataset_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["episode"], 1)
        self.assertEqual(record["score"], 42.5)


if __name__ == "__main__":
    unittest.main()
