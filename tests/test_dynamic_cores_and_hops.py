import pathlib
import sys
import unittest

MODULE_DIR = pathlib.Path(__file__).resolve().parents[1]
src_dir = MODULE_DIR / "src"
sys.path.insert(0, str(src_dir) if src_dir.is_dir() else str(MODULE_DIR))

import geometry as G
from server import (
    DEFAULT_SETTINGS,
    FloorEnvironment,
    ParallelTrainer,
    SettingsError,
    _max_cores_for_site,
    validate_settings_patch,
)


class TestDynamicCoresAndHops(unittest.TestCase):
    def test_max_cores_for_site_scaling(self) -> None:
        # Small sites get 2 cores
        self.assertEqual(_max_cores_for_site(500.0), 2)
        self.assertEqual(_max_cores_for_site(1200.0), 2)
        # Medium/Large sites scale up to 8
        self.assertEqual(_max_cores_for_site(2500.0), 4)
        self.assertEqual(_max_cores_for_site(5000.0), 8)
        self.assertEqual(_max_cores_for_site(10000.0), 8)

    def test_settings_max_room_hops_validation(self) -> None:
        # Default value is 3
        self.assertEqual(DEFAULT_SETTINGS["maxRoomHops"], 3)

        # Valid range [1, 10]
        patch = validate_settings_patch(DEFAULT_SETTINGS, {"maxRoomHops": 6})
        self.assertEqual(patch["maxRoomHops"], 6)

        patch_min = validate_settings_patch(DEFAULT_SETTINGS, {"maxRoomHops": 1})
        self.assertEqual(patch_min["maxRoomHops"], 1)

        patch_max = validate_settings_patch(DEFAULT_SETTINGS, {"maxRoomHops": 10})
        self.assertEqual(patch_max["maxRoomHops"], 10)

        # Out of bounds raises SettingsError
        with self.assertRaises(SettingsError):
            validate_settings_patch(DEFAULT_SETTINGS, {"maxRoomHops": 0})

        with self.assertRaises(SettingsError):
            validate_settings_patch(DEFAULT_SETTINGS, {"maxRoomHops": 11})

        with self.assertRaises(SettingsError):
            validate_settings_patch(DEFAULT_SETTINGS, {"maxRoomHops": "five"})

    def test_large_site_multi_core_expansion(self) -> None:
        settings = dict(DEFAULT_SETTINGS)
        settings["siteAreaTier"] = "XL"
        settings["boundaryType"] = "lobed"
        settings["seed"] = 42
        settings["parallelEnvironments"] = 4
        settings["maxModules"] = 180
        settings["maxRoomHops"] = 5
        settings["allowStop"] = False

        trainer = ParallelTrainer(settings)
        trainer.new_site()
        trainer.set_mode("inference")

        max_steps = 200
        event = None
        for _ in range(max_steps):
            event = trainer.step(trainer.generation_id, trainer.episode)
            if event.get("type") == "episodeDone":
                break

        self.assertIsNotNone(event)
        self.assertEqual(event.get("type"), "episodeDone")
        placements = event.get("placements", [])
        cores = [p for p in placements if p.get("category") == "core" or p.get("module", {}).get("category") == "core"]
        self.assertGreaterEqual(len(cores), 4, "Large multi-floor site should support multiple cores across floors")
        metrics = event.get("metrics", {})
        self.assertGreater(float(metrics.get("fillRatio", 0.0)), 0.50, "Large site fill ratio should exceed 50%")


if __name__ == "__main__":
    unittest.main()
