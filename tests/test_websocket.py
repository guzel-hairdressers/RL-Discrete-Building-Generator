"""End-to-end WebSocket protocol regressions."""

from __future__ import annotations

import math
import pathlib
import sys
import unittest

from fastapi.testclient import TestClient


MODULE_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

import server  # noqa: E402


def polygon_geometry_signature(polygon: list[dict]) -> tuple[tuple[float, float, float], ...]:
    """Identify a polygon up to translation, common rotation, and cyclic start.

    Edge lengths plus signed normalized turns distinguish both angle structure
    and chirality; reflection reverses the cross-product signs.
    """

    edges = []
    for index, start in enumerate(polygon):
        end = polygon[(index + 1) % len(polygon)]
        dx = float(end["x"]) - float(start["x"])
        dy = float(end["y"]) - float(start["y"])
        length = math.hypot(dx, dy)
        if length <= 1.0e-9:
            raise AssertionError("protocol polygon contains a degenerate edge")
        edges.append((dx, dy, length))

    features = []
    for index, (dx, dy, length) in enumerate(edges):
        next_dx, next_dy, next_length = edges[(index + 1) % len(edges)]
        scale = length * next_length
        features.append(
            (
                round(length, 6),
                round((dx * next_dx + dy * next_dy) / scale, 7),
                round((dx * next_dy - dy * next_dx) / scale, 7),
            )
        )
    rotations = [
        tuple(features[offset:] + features[:offset])
        for offset in range(len(features))
    ]
    return min(rotations)


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
                self.assertEqual(len(final_event["nextDictionary"]), 6)
                self.assertIn("mergedPlacements", final_event)
                completed_dictionary_geometry = {
                    module["id"]: polygon_geometry_signature(module["poly"])
                    for module in final_event["dictionary"]
                }
                next_dictionary_geometry = {
                    module["id"]: polygon_geometry_signature(module["poly"])
                    for module in final_event["nextDictionary"]
                }
                changed_slots = {
                    module_id
                    for module_id, signature in completed_dictionary_geometry.items()
                    if next_dictionary_geometry.get(module_id) != signature
                }
                self.assertTrue(
                    changed_slots,
                    "deterministic regression seed must distinguish completed and next palettes",
                )
                for placement in final_event["placements"]:
                    module_id = placement["module"]["id"]
                    self.assertIn(module_id, completed_dictionary_geometry)
                    self.assertEqual(
                        polygon_geometry_signature(placement["poly"]),
                        completed_dictionary_geometry[module_id],
                        f"placement {placement['id']} does not match completed card {module_id}",
                    )
                individual_area = sum(
                    server.G.polygon_area(placement["poly"])
                    for placement in final_event["placements"]
                )
                merged_area = sum(
                    server.G.polygon_area(placement["poly"])
                    for placement in final_event["mergedPlacements"]
                )
                self.assertAlmostEqual(merged_area, individual_area, places=5)
                individual_ids = {placement["id"] for placement in final_event["placements"]}
                component_ids = {
                    component["id"]
                    for placement in final_event["mergedPlacements"]
                    for component in placement.get("components", [])
                }
                self.assertEqual(component_ids, individual_ids)
                dictionary_ids = {module["id"] for module in final_event["mergedDictionary"]}
                for placement in final_event["mergedPlacements"]:
                    module_id = placement["module"]["id"]
                    if module_id.startswith("M_round"):
                        self.assertIn(module_id, dictionary_ids)


if __name__ == "__main__":
    unittest.main()
