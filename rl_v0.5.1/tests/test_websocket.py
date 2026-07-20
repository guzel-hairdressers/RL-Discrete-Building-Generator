"""End-to-end WebSocket protocol regressions."""

from __future__ import annotations

import pathlib
import sys
import unittest

from fastapi.testclient import TestClient


MODULE_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

import server  # noqa: E402


class WebSocketProtocolTests(unittest.TestCase):
    def test_settings_site_step_stale_guard_and_new_generation(self) -> None:
        with TestClient(server.app) as client:
            with client.websocket_connect("/ws") as websocket:
                websocket.send_json(
                    {
                        "cmd": "updateSettings",
                        "settings": {
                            "boundaryType": "rect",
                            "atriumPolicy": "none",
                            "parallelEnvironments": 1,
                            "maxModules": 10,
                            "dictCap": 6,
                            "angleStep": 90.0,
                            "seed": 440,
                        },
                    }
                )
                acknowledgement = websocket.receive_json()
                site = websocket.receive_json()
                self.assertEqual(acknowledgement["type"], "ack")
                self.assertEqual(acknowledgement["command"], "updateSettings")
                self.assertEqual(site["type"], "site")
                self.assertEqual(len(site["boundaries"]), 1)

                generation = site["generationId"]
                episode = site["episode"]
                websocket.send_json(
                    {"cmd": "step", "generationId": generation, "episode": episode}
                )
                placement_event = websocket.receive_json()
                self.assertEqual(placement_event["type"], "placements")
                self.assertEqual(placement_event["generationId"], generation)
                self.assertEqual(placement_event["episode"], episode)
                self.assertEqual(len(placement_event["placements"]), 1)
                self.assertEqual(placement_event["placements"][0]["module"]["category"], "core")

                websocket.send_json(
                    {"cmd": "step", "generationId": generation - 1, "episode": episode}
                )
                stale = websocket.receive_json()
                self.assertEqual(stale["type"], "error")
                self.assertEqual(stale["code"], "stale_generation")
                self.assertTrue(stale["recoverable"])

                websocket.send_json({"cmd": "updateSettings", "settings": {"angleStep": 0.25}})
                invalid = websocket.receive_json()
                self.assertEqual(invalid["type"], "error")
                self.assertEqual(invalid["code"], "invalid_settings")
                self.assertEqual(invalid["generationId"], generation)

                websocket.send_json({"cmd": "newSite"})
                replacement = websocket.receive_json()
                self.assertEqual(replacement["type"], "site")
                self.assertEqual(replacement["generationId"], generation + 1)

    def test_complete_episode_backpropagates_across_worker_thread_steps(self) -> None:
        with TestClient(server.app) as client:
            with client.websocket_connect("/ws") as websocket:
                websocket.send_json(
                    {
                        "cmd": "updateSettings",
                        "settings": {
                            "boundaryType": "rect",
                            "atriumPolicy": "none",
                            "parallelEnvironments": 1,
                            "maxModules": 10,
                            "dictCap": 6,
                            "angleStep": 0.0,
                            "seed": 928,
                        },
                    }
                )
                websocket.receive_json()
                site = websocket.receive_json()
                final_event = None
                for _ in range(20):
                    websocket.send_json(
                        {
                            "cmd": "step",
                            "generationId": site["generationId"],
                            "episode": site["episode"],
                        }
                    )
                    event = websocket.receive_json()
                    if event["type"] == "episodeDone":
                        final_event = event
                        break
                self.assertIsNotNone(final_event)
                self.assertEqual(final_event["nextEpisode"], site["episode"] + 1)
                self.assertIn("policyLoss", final_event["metrics"])
                self.assertIn("topologyMultiplier", final_event["metrics"])
                self.assertEqual(len(final_event["dictionary"]), 6)


if __name__ == "__main__":
    unittest.main()
