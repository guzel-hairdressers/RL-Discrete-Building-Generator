"""Regression tests for the exact-vector v0.3 geometry kernel."""

from __future__ import annotations

import math
import pathlib
import sys
import unittest


MODULE_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

import geometry as G  # noqa: E402


def rectangle(x: float, y: float, width: float, height: float) -> list[dict[str, float]]:
    return [
        {"x": x, "y": y},
        {"x": x + width, "y": y},
        {"x": x + width, "y": y + height},
        {"x": x, "y": y + height},
    ]


class StrictContactTests(unittest.TestCase):
    def test_shared_overlap_threshold_inputs_are_exact_and_symmetric(self) -> None:
        base = rectangle(0.0, 0.0, 4.0, 2.0)
        cases = (
            (rectangle(4.0, 1.51, 2.0, 2.0), 0.49),
            (rectangle(4.0, 1.50, 2.0, 2.0), 0.50),
            (rectangle(4.0, 1.49, 2.0, 2.0), 0.51),
        )
        for neighbor, expected in cases:
            with self.subTest(expected=expected):
                forward = G.get_shared_overlap(base, neighbor)
                reverse = G.get_shared_overlap(neighbor, base)
                self.assertAlmostEqual(forward, expected, places=7)
                self.assertAlmostEqual(reverse, expected, places=7)

    def test_gap_skew_and_vertex_touch_do_not_create_edges(self) -> None:
        base = rectangle(0.0, 0.0, 4.0, 1.0)
        gap = rectangle(0.0, 1.04, 4.0, 1.0)
        vertex = rectangle(4.0, 1.0, 2.0, 2.0)
        skew = [
            {"x": 0.0, "y": 1.04},
            {"x": 4.0, "y": 1.44},
            {"x": 4.0, "y": 2.44},
            {"x": 0.0, "y": 2.04},
        ]
        for other in (gap, vertex, skew):
            with self.subTest(other=other):
                self.assertEqual(G.get_shared_overlap(base, other), 0.0)
                self.assertEqual(G.get_shared_overlap(other, base), 0.0)

    def test_overlap_distinguishes_interior_area_from_boundary_contact(self) -> None:
        first = rectangle(0.0, 0.0, 2.0, 2.0)
        identical = rectangle(0.0, 0.0, 2.0, 2.0)
        contained = rectangle(0.5, 0.5, 0.5, 0.5)
        adjacent = rectangle(2.0, 0.0, 2.0, 2.0)
        self.assertTrue(G.polygons_overlap(first, identical))
        self.assertTrue(G.polygons_overlap(first, contained))
        self.assertFalse(G.polygons_overlap(first, adjacent))

    def test_longest_contact_does_not_sum_disjoint_short_fragments(self) -> None:
        base = rectangle(0.0, 0.0, 2.0, 1.0)
        two_teeth = [
            {"x": 0.0, "y": 1.0},
            {"x": 0.3, "y": 1.0},
            {"x": 0.3, "y": 1.2},
            {"x": 1.7, "y": 1.2},
            {"x": 1.7, "y": 1.0},
            {"x": 2.0, "y": 1.0},
            {"x": 2.0, "y": 2.0},
            {"x": 0.0, "y": 2.0},
        ]
        self.assertAlmostEqual(G.get_shared_overlap(base, two_teeth), 0.6, places=7)
        self.assertAlmostEqual(G.max_shared_overlap(base, two_teeth), 0.3, places=7)
        self.assertAlmostEqual(G.max_shared_overlap(two_teeth, base), 0.3, places=7)


class ExactEnvelopeTests(unittest.TestCase):
    def test_shared_wall_is_removed_without_losing_diagonals(self) -> None:
        first = rectangle(0.0, 0.0, 1.0, 1.0)
        second = rectangle(1.0, 0.0, 1.0, 1.0)
        segments = G.exposed_wall_segments([first, second])
        self.assertAlmostEqual(sum(segment["length"] for segment in segments), 6.0, places=7)

        triangle = [
            {"x": 0.0, "y": 0.0},
            {"x": 2.0, "y": 0.0},
            {"x": 1.0, "y": math.sqrt(3.0)},
        ]
        triangle_segments = G.exposed_wall_segments([triangle])
        self.assertEqual(len(triangle_segments), 3)
        self.assertTrue(
            any(
                abs(segment["a"]["x"] - segment["b"]["x"]) > 1e-6
                and abs(segment["a"]["y"] - segment["b"]["y"]) > 1e-6
                for segment in triangle_segments
            )
        )

    def test_point_distance_uses_original_vector_segment(self) -> None:
        diagonal = [{"a": {"x": 0.0, "y": 0.0}, "b": {"x": 2.0, "y": 2.0}}]
        self.assertAlmostEqual(
            G.point_to_segments_dist({"x": 1.0, "y": 0.0}, diagonal),
            math.sqrt(0.5),
            places=7,
        )


class ProceduralGeometryTests(unittest.TestCase):
    def test_zero_degree_increment_is_a_supported_single_orientation(self) -> None:
        rotations = G.normalize_rotations(rectangle(0.0, 0.0, 3.0, 2.0), 0.0)
        self.assertEqual(len(rotations), 1)
        self.assertEqual(rotations[0]["angle"], 0.0)

    def test_atrium_candidates_never_advertise_empty_named_holes(self) -> None:
        for boundary_type in ("lobed", "lshape", "ushape", "tshape", "convex", "rect", "free"):
            for seed in range(3):
                with self.subTest(boundary_type=boundary_type, seed=seed):
                    boundary = G.make_boundary(boundary_type, seed, {})
                    candidates = G.atrium_candidates(boundary, G.RNG(seed + 1000))
                    self.assertEqual(candidates[0]["id"], "none")
                    for candidate in candidates[1:]:
                        self.assertTrue(candidate["holes"])
                        for hole in candidate["holes"]:
                            self.assertTrue(G.polygon_inside_site(hole, boundary["outer"], []))

    def test_default_pool_has_legal_flexible_roles(self) -> None:
        settings = {
            "minEdge": 1.5,
            "maxEdge": 9.0,
            "maxEdges": 8,
            "publicMode": False,
            "allowCorridors": True,
        }
        pool = G.generate_module_pool(settings, G.RNG(9123), count=120)
        categories = {candidate["category"] for candidate in pool}
        self.assertTrue({"core", "corridor", "room"}.issubset(categories))
        self.assertNotIn("special", categories)

        for candidate in pool:
            poly = candidate["poly"]
            self.assertTrue(G.is_simple_polygon(poly))
            self.assertGreater(G.polygon_area(poly), 0.0)
            self.assertGreaterEqual(min(G.internal_angles(poly)), 40.0 - 1e-6)
            self.assertLessEqual(len(poly), settings["maxEdges"])
            if candidate["category"] == "core":
                self.assertGreaterEqual(candidate["area"], 20.0 - 1e-6)
                self.assertLessEqual(candidate["area"], 30.0 + 1e-6)
            if candidate["category"] == "corridor":
                self.assertLessEqual(G.min_polygon_width(poly), 1.5 + 1e-6)

    def test_single_floor_pool_still_contains_core_candidates(self) -> None:
        settings = {
            "minEdge": 1.5,
            "maxEdge": 9.0,
            "maxEdges": 8,
            "publicMode": False,
            "singleFloor": True,
        }
        pool = G.generate_module_pool(settings, G.RNG(2217), count=32)
        cores = [candidate for candidate in pool if candidate["category"] == "core"]
        self.assertGreaterEqual(len(cores), 3)
        for core in cores:
            self.assertGreaterEqual(core["area"], 20.0 - 1e-6)
            self.assertLessEqual(core["area"], 30.0 + 1e-6)

    def test_three_edge_cap_generates_valid_triangle_corridors(self) -> None:
        settings = {
            "minEdge": 1.5,
            "maxEdge": 9.0,
            "maxEdges": 3,
            "publicMode": True,
            "singleFloor": False,
            "allowCorridors": True,
        }
        pool = G.generate_module_pool(settings, G.RNG(3319), count=36)
        corridors = [candidate for candidate in pool if candidate["category"] == "corridor"]
        self.assertGreaterEqual(len(corridors), 3)
        self.assertTrue(all(len(candidate["poly"]) <= 3 for candidate in pool))
        for corridor in corridors:
            poly = corridor["poly"]
            self.assertEqual(len(poly), 3)
            self.assertEqual(corridor["parameters"]["generator"], "narrow-triangle")
            self.assertTrue(corridor["edgeRangeCompatible"])
            self.assertGreaterEqual(min(G.internal_angles(poly)), 40.0 - 1e-6)
            self.assertLessEqual(G.min_polygon_width(poly), 1.5 + 1e-6)
            self.assertGreaterEqual(min(corridor["parameters"]["edgeLengths"]), settings["minEdge"] - 1e-6)
            self.assertLessEqual(max(corridor["parameters"]["edgeLengths"]), settings["maxEdge"] + 1e-6)

    def test_every_module_has_canonical_horizontal_connection_edges(self) -> None:
        settings = {
            "minEdge": 1.5,
            "maxEdge": 9.0,
            "maxEdges": 8,
            "publicMode": True,
        }
        pool = G.generate_module_pool(settings, G.RNG(4481), count=48)

        def horizontal_edges(module):
            poly = module["poly"]
            return [
                (index, poly[index], poly[(index + 1) % len(poly)])
                for index in range(len(poly))
                if abs(poly[index]["y"] - poly[(index + 1) % len(poly)]["y"]) <= 1e-9
            ]

        for module in pool:
            edges = horizontal_edges(module)
            self.assertTrue(edges, module["id"])
            connection = module["parameters"]["connectionEdge"]
            self.assertIn(connection["index"], [edge[0] for edge in edges])
            edge = next(edge for edge in edges if edge[0] == connection["index"])
            self.assertAlmostEqual(
                math.hypot(edge[2]["x"] - edge[1]["x"], edge[2]["y"] - edge[1]["y"]),
                connection["length"],
                places=7,
            )
            if len(module["poly"]) > 3 and not module["id"].startswith("Q_irreg"):
                vectors = [
                    (edge[2]["x"] - edge[1]["x"], edge[2]["y"] - edge[1]["y"])
                    for edge in edges
                ]
                self.assertTrue(
                    any(
                        first[0] * second[0] + first[1] * second[1] < 0.0
                        for first in vectors
                        for second in vectors
                    ),
                    module["id"],
                )

        core = next(module for module in pool if module["category"] == "core" and len(module["poly"]) > 3 and not module["id"].startswith("Q_irreg"))
        room = next(module for module in pool if module["category"] == "room" and len(module["poly"]) > 3 and not module["id"].startswith("Q_irreg"))
        core_index = core["parameters"]["connectionEdge"]["index"]
        room_index = room["parameters"]["connectionEdge"]["oppositeIndex"]
        self.assertIsNotNone(room_index)
        core_start = core["poly"][core_index]
        core_end = core["poly"][(core_index + 1) % len(core["poly"])]
        room_start = room["poly"][room_index]
        translated_room = G.translate_polygon(
            room["poly"],
            core_end["x"] - room_start["x"],
            core_end["y"] - room_start["y"],
        )
        self.assertGreaterEqual(G.max_shared_overlap(core["poly"], translated_room), 0.5)
        self.assertFalse(G.polygons_overlap(core["poly"], translated_room))

    def test_corridor_supports_two_metre_edges_with_narrow_true_width(self) -> None:
        settings = {
            "minEdge": 2.0,
            "maxEdge": 9.0,
            "maxEdges": 8,
            "publicMode": False,
            "allowCorridors": True,
        }
        pool = G.generate_module_pool(settings, G.RNG(5591), count=36)
        corridors = [module for module in pool if module["category"] == "corridor"]
        self.assertTrue(corridors)
        for corridor in corridors:
            self.assertTrue(corridor["edgeRangeCompatible"])
            self.assertGreaterEqual(min(corridor["parameters"]["edgeLengths"]), 2.0 - 1e-6)
            self.assertLessEqual(G.min_polygon_width(corridor["poly"]), 1.5 + 1e-6)
            self.assertGreaterEqual(min(G.internal_angles(corridor["poly"])), 40.0 - 1e-6)

    def test_latent_module_bridge_is_deterministic_and_constrained(self) -> None:
        settings = {
            "minEdge": 1.5,
            "maxEdge": 9.0,
            "maxEdges": 8,
            "publicMode": True,
            "allowCorridors": True,
        }
        latent = [0.63, 0.71, 0.28, 0.82, 0.19, 0.91]
        for category in ("core", "room", "special", "corridor"):
            with self.subTest(category=category):
                first = G.synthesize_module_from_latent(settings, category, latent, f"L-{category}")
                second = G.synthesize_module_from_latent(settings, category, latent, f"L-{category}")
                self.assertEqual(first, second)
                self.assertTrue(first["learnedGeometry"])
                self.assertEqual(first["category"], category)
                self.assertTrue(first["edgeRangeCompatible"])
                self.assertTrue(G.is_simple_polygon(first["poly"]))
                self.assertLessEqual(len(first["poly"]), settings["maxEdges"])
                self.assertGreaterEqual(min(G.internal_angles(first["poly"])), 40.0 - 1e-6)
                self.assertGreaterEqual(min(first["parameters"]["edgeLengths"]), settings["minEdge"] - 1e-6)
                self.assertLessEqual(max(first["parameters"]["edgeLengths"]), settings["maxEdge"] + 1e-6)
                self.assertEqual(first["parameters"]["latent"]["input"], latent)
                self.assertIn("connectionEdge", first["parameters"])
                if category == "core":
                    self.assertGreaterEqual(first["area"], 20.0)
                    self.assertLessEqual(first["area"], 30.0)
                if category == "room":
                    self.assertGreaterEqual(first["area"], 8.0)
                    self.assertLessEqual(first["area"], 24.5)
                if category == "special":
                    self.assertGreaterEqual(first["area"], 26.0)
                    self.assertLessEqual(first["area"], 46.0)
                if category == "corridor":
                    self.assertLessEqual(G.min_polygon_width(first["poly"]), 1.5 + 1e-6)

        with self.assertRaises(ValueError):
            G.synthesize_module_from_latent(
                {**settings, "publicMode": False},
                "special",
                latent,
                "forbidden-special",
            )
        with self.assertRaises(ValueError):
            G.synthesize_module_from_latent(settings, "room", [1.01, 0.2], "bad-latent")

    def test_latent_dimensions_materially_change_generated_geometry(self) -> None:
        settings = {
            "minEdge": 1.5,
            "maxEdge": 9.0,
            "maxEdges": 8,
            "publicMode": True,
        }
        low = G.synthesize_module_from_latent(
            settings,
            "core",
            [0.1, 0.1, 0.1, 0.1, 0.1, 0.1],
            "latent-low",
        )
        high = G.synthesize_module_from_latent(
            settings,
            "core",
            [0.9, 0.9, 0.9, 0.9, 0.9, 0.9],
            "latent-high",
        )
        self.assertAlmostEqual(low["area"], 21.0, places=6)
        self.assertAlmostEqual(high["area"], 29.0, places=6)
        self.assertNotEqual(len(low["poly"]), len(high["poly"]))
        self.assertNotEqual(low["parameters"]["targetAspect"], high["parameters"]["targetAspect"])
        self.assertFalse(low["parameters"]["requestedConcavity"])
        self.assertTrue(high["parameters"]["requestedConcavity"])
        self.assertNotEqual(low["poly"], high["poly"])

        corridor_left = G.synthesize_module_from_latent(
            settings,
            "corridor",
            [0.5, 0.5, 0.5, 0.5, 0.1, 0.5],
            "corridor-left",
        )
        corridor_right = G.synthesize_module_from_latent(
            settings,
            "corridor",
            [0.5, 0.5, 0.5, 0.5, 0.9, 0.5],
            "corridor-right",
        )
        self.assertLess(corridor_left["parameters"]["shear"], 0.0)
        self.assertGreater(corridor_right["parameters"]["shear"], 0.0)
        self.assertNotEqual(corridor_left["poly"], corridor_right["poly"])


if __name__ == "__main__":
    unittest.main()
