"""Differential tests for the optional native vector-geometry backend."""

from __future__ import annotations

import math
import pathlib
import random
import sys
import unittest


MODULE_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

import geometry as G  # noqa: E402


def point(x: float, y: float) -> dict[str, float]:
    return {"x": float(x), "y": float(y)}


def rectangle(
    x: float, y: float, width: float, height: float
) -> list[dict[str, float]]:
    return [
        point(x, y),
        point(x + width, y),
        point(x + width, y + height),
        point(x, y + height),
    ]


def radial_polygon(
    rng: random.Random,
    center_x: float,
    center_y: float,
    radius: float,
    vertices: int,
) -> list[dict[str, float]]:
    """Make a deterministic simple polygon with varied edge directions."""

    angle_offset = rng.uniform(-math.pi, math.pi)
    result = []
    for index in range(vertices):
        angle = angle_offset + math.tau * index / vertices
        local_radius = radius * rng.uniform(0.65, 1.0)
        result.append(
            point(
                center_x + math.cos(angle) * local_radius,
                center_y + math.sin(angle) * local_radius,
            )
        )
    return result


@unittest.skipUnless(
    G.NATIVE_GEOMETRY_AVAILABLE,
    "build the optional native backend with build_native.py",
)
class NativeGeometryParityTests(unittest.TestCase):
    def test_native_status_reports_loaded_compatible_library(self) -> None:
        status = G.native_geometry_status()
        self.assertTrue(status["available"])
        self.assertEqual(status["abiVersion"], G.NATIVE_GEOMETRY_ABI_VERSION)
        self.assertIsInstance(status["library"], str)
        self.assertTrue(pathlib.Path(status["library"]).is_file())
        self.assertIsNone(status["loadError"])

    def test_overlap_matches_reference_for_contact_and_concavity(self) -> None:
        square = rectangle(0.0, 0.0, 4.0, 4.0)
        concave = [
            point(0.0, 0.0),
            point(5.0, 0.0),
            point(5.0, 5.0),
            point(3.0, 5.0),
            point(3.0, 2.0),
            point(2.0, 2.0),
            point(2.0, 5.0),
            point(0.0, 5.0),
        ]
        cases = (
            (square, rectangle(0.0, 0.0, 4.0, 4.0)),
            (square, rectangle(1.0, 1.0, 1.0, 1.0)),
            (square, rectangle(4.0, 0.0, 2.0, 2.0)),
            (square, rectangle(4.0, 4.0, 2.0, 2.0)),
            (square, rectangle(3.5, 3.5, 2.0, 2.0)),
            (concave, rectangle(2.25, 2.5, 0.5, 1.0)),
            (concave, rectangle(0.5, 2.5, 1.0, 1.0)),
        )
        for first, second in cases:
            with self.subTest(first=first, second=second):
                expected = G._polygons_overlap_python(first, second)
                self.assertEqual(G._native_polygons_overlap(first, second), expected)
                self.assertEqual(G._native_polygons_overlap(second, first), expected)

    def test_concave_boundary_escape_uses_all_split_intervals(self) -> None:
        # Every vertex and every whole-edge midpoint is legal, but the long
        # diagonal exits through the U-shaped notch and later re-enters.
        outer = [
            point(0.0, 0.0),
            point(6.0, 0.0),
            point(6.0, 6.0),
            point(4.0, 6.0),
            point(4.0, 2.0),
            point(2.0, 2.0),
            point(2.0, 6.0),
            point(0.0, 6.0),
        ]
        escaping_triangle = [
            point(0.5, 0.5),
            point(4.0, 2.5),
            point(0.5, 1.0),
        ]
        samples = escaping_triangle + [
            G._edge_midpoint(first, escaping_triangle[(index + 1) % 3])
            for index, first in enumerate(escaping_triangle)
        ]
        self.assertTrue(
            all(
                G.point_in_polygon(sample, outer)
                or G.point_on_polygon(sample, outer)
                for sample in samples
            )
        )
        self.assertFalse(G._polygon_inside_site_python(escaping_triangle, outer, []))
        self.assertFalse(G._native_polygon_inside_site(escaping_triangle, outer, []))

    def test_containment_and_hole_contact_match_reference(self) -> None:
        outer = rectangle(0.0, 0.0, 10.0, 10.0)
        hole = rectangle(4.0, 4.0, 2.0, 2.0)
        bow_tie = [point(1.0, 1.0), point(3.0, 3.0), point(1.0, 3.0), point(3.0, 1.0)]
        cases = (
            (rectangle(1.0, 1.0, 2.0, 2.0), True),
            (rectangle(0.0, 0.0, 2.0, 2.0), True),
            (rectangle(3.5, 4.5, 2.0, 1.0), False),
            (rectangle(4.25, 4.25, 0.5, 0.5), False),
            (rectangle(2.0, 4.0, 2.0, 2.0), True),
            (rectangle(9.0, 9.0, 2.0, 2.0), False),
            (bow_tie, False),
        )
        for candidate, expected in cases:
            with self.subTest(candidate=candidate):
                reference = G._polygon_inside_site_python(candidate, outer, [hole])
                native = G._native_polygon_inside_site(candidate, outer, [hole])
                self.assertEqual(reference, expected)
                self.assertEqual(native, reference)

    def test_shared_overlap_pair_matches_total_and_longest_fragments(self) -> None:
        base = rectangle(0.0, 0.0, 2.0, 1.0)
        two_teeth = [
            point(0.0, 1.0),
            point(0.3, 1.0),
            point(0.3, 1.2),
            point(1.7, 1.2),
            point(1.7, 1.0),
            point(2.0, 1.0),
            point(2.0, 2.0),
            point(0.0, 2.0),
        ]
        expected = G._shared_overlap_pair_python(base, two_teeth)
        native = G._native_shared_overlap_pair(base, two_teeth)
        self.assertAlmostEqual(expected[0], 0.3, places=7)
        self.assertAlmostEqual(expected[1], 0.6, places=7)
        self.assertAlmostEqual(native[0], expected[0], places=12)
        self.assertAlmostEqual(native[1], expected[1], places=12)
        reverse = G._native_shared_overlap_pair(two_teeth, base)
        self.assertAlmostEqual(reverse[0], expected[0], places=12)
        self.assertAlmostEqual(reverse[1], expected[1], places=12)

    def test_length_scaled_collinearity_matches_reference(self) -> None:
        distance = 1_000_000.0
        first = [
            point(0.0, 0.0),
            point(distance, distance),
            point(-200.0, 400.0),
        ]
        for offset, should_match in ((3.0e-8, True), (2.0e-7, False)):
            second = [
                point(250_000.0 + offset, 250_000.0 - offset),
                point(750_000.0 + offset, 750_000.0 - offset),
                point(750_400.0, 749_800.0),
            ]
            with self.subTest(offset=offset):
                expected = G._shared_overlap_pair_python(first, second)
                native = G._native_shared_overlap_pair(first, second)
                if should_match:
                    self.assertGreater(expected[0], 700_000.0)
                else:
                    self.assertEqual(expected, (0.0, 0.0))
                self.assertAlmostEqual(native[0], expected[0], places=7)
                self.assertAlmostEqual(native[1], expected[1], places=7)

    def test_tolerant_segment_overlap_matches_python_bpe_contract(self) -> None:
        rng = random.Random(0xB0E)
        G._native_symmetric_segment_overlap_values.cache_clear()
        for index in range(1000):
            angle = rng.uniform(-math.pi, math.pi)
            first_length = rng.uniform(0.25, 12.0)
            second_length = rng.uniform(0.25, 12.0)
            first = point(rng.uniform(-20.0, 20.0), rng.uniform(-20.0, 20.0))
            second = point(
                first["x"] + math.cos(angle) * first_length,
                first["y"] + math.sin(angle) * first_length,
            )
            along = rng.uniform(-0.5, 1.5) * first_length
            normal_offset = rng.uniform(-0.015, 0.015)
            skew = rng.uniform(-0.002, 0.002)
            third = point(
                first["x"] + math.cos(angle) * along - math.sin(angle) * normal_offset,
                first["y"] + math.sin(angle) * along + math.cos(angle) * normal_offset,
            )
            fourth = point(
                third["x"] + math.cos(angle + skew) * second_length,
                third["y"] + math.sin(angle + skew) * second_length,
            )
            expected = G._symmetric_segment_overlap_python(
                first, second, third, fourth, 1.0e-2, 1.0e-3
            )
            actual = G._native_symmetric_segment_overlap_values(
                first["x"],
                first["y"],
                second["x"],
                second["y"],
                third["x"],
                third["y"],
                fourth["x"],
                fourth["y"],
                1.0e-2,
                1.0e-3,
            )
            with self.subTest(index=index):
                self.assertEqual(actual is None, expected is None)
                if expected is not None and actual is not None:
                    for actual_interval, expected_interval in zip(actual[:2], expected[:2]):
                        self.assertAlmostEqual(actual_interval[0], expected_interval[0], places=12)
                        self.assertAlmostEqual(actual_interval[1], expected_interval[1], places=12)
                    self.assertAlmostEqual(actual[2], expected[2], places=12)

    def test_point_to_segment_distance_matches_reference(self) -> None:
        rng = random.Random(0xD157)
        for index in range(500):
            segments = [
                (
                    point(rng.uniform(-30.0, 30.0), rng.uniform(-30.0, 30.0)),
                    point(rng.uniform(-30.0, 30.0), rng.uniform(-30.0, 30.0)),
                )
                for _ in range(rng.randint(1, 40))
            ]
            probe = point(rng.uniform(-30.0, 30.0), rng.uniform(-30.0, 30.0))
            expected = G._point_to_segments_dist_python(probe, segments)
            actual = G.point_to_segments_dist(probe, segments)
            with self.subTest(index=index):
                self.assertAlmostEqual(actual, expected, places=12)

    def test_deterministic_randomized_overlap_parity(self) -> None:
        rng = random.Random(0xC0FFEE)
        for index in range(500):
            first = radial_polygon(
                rng,
                rng.uniform(-4.0, 4.0),
                rng.uniform(-4.0, 4.0),
                rng.uniform(0.25, 3.0),
                rng.randint(3, 9),
            )
            second = radial_polygon(
                rng,
                rng.uniform(-4.0, 4.0),
                rng.uniform(-4.0, 4.0),
                rng.uniform(0.25, 3.0),
                rng.randint(3, 9),
            )
            with self.subTest(index=index):
                self.assertEqual(
                    G._native_polygons_overlap(first, second),
                    G._polygons_overlap_python(first, second),
                )
                native_pair = G._native_shared_overlap_pair(first, second)
                reference_pair = G._shared_overlap_pair_python(first, second)
                self.assertAlmostEqual(native_pair[0], reference_pair[0], places=12)
                self.assertAlmostEqual(native_pair[1], reference_pair[1], places=12)

    def test_deterministic_randomized_containment_parity(self) -> None:
        rng = random.Random(0x51E)
        case_index = 0
        for boundary_type in (
            "lobed",
            "lshape",
            "ushape",
            "tshape",
            "convex",
            "rect",
            "free",
        ):
            for seed in range(5):
                outer = G.make_boundary(boundary_type, seed, {})["outer"]
                bounds = G.bounds_of(outer)
                width = bounds["maxX"] - bounds["minX"]
                height = bounds["maxY"] - bounds["minY"]
                for _ in range(10):
                    candidate = radial_polygon(
                        rng,
                        rng.uniform(bounds["minX"] - 0.1 * width, bounds["maxX"] + 0.1 * width),
                        rng.uniform(bounds["minY"] - 0.1 * height, bounds["maxY"] + 0.1 * height),
                        rng.uniform(0.01, 0.12) * min(width, height),
                        rng.randint(3, 7),
                    )
                    with self.subTest(index=case_index, boundary=boundary_type):
                        self.assertEqual(
                            G._native_polygon_inside_site(candidate, outer, []),
                            G._polygon_inside_site_python(candidate, outer, []),
                        )
                    case_index += 1

    def test_value_keyed_buffers_are_reused_without_aliasing_mutable_polygons(self) -> None:
        G._packed_polygon_from_signature.cache_clear()
        first = rectangle(0.0, 0.0, 2.0, 2.0)
        second = rectangle(1.0, 1.0, 2.0, 2.0)
        G._native_polygons_overlap(first, second)
        initial = G._packed_polygon_from_signature.cache_info()

        # Equal values in new mutable containers may safely reuse the buffers.
        G._native_polygons_overlap(list(map(dict, first)), list(map(dict, second)))
        reused = G._packed_polygon_from_signature.cache_info()
        self.assertGreaterEqual(reused.hits - initial.hits, 2)

        # A later source mutation creates a new value signature and buffer.
        first[0]["x"] = -1.0
        G._native_polygons_overlap(first, second)
        mutated = G._packed_polygon_from_signature.cache_info()
        self.assertGreater(mutated.misses, reused.misses)

    def test_runtime_dispatch_can_be_disabled_and_restored(self) -> None:
        first = rectangle(0.0, 0.0, 2.0, 2.0)
        second = rectangle(1.0, 1.0, 2.0, 2.0)
        original = G.NATIVE_GEOMETRY_ENABLED
        try:
            self.assertFalse(G.set_native_geometry_enabled(False))
            self.assertFalse(G.native_geometry_status()["enabled"])
            self.assertEqual(
                G.polygons_overlap(first, second),
                G._polygons_overlap_python(first, second),
            )
            self.assertTrue(G.set_native_geometry_enabled(True))
            self.assertTrue(G.native_geometry_status()["enabled"])
            self.assertEqual(
                G.shared_overlap_pair(first, second),
                G._native_shared_overlap_pair(first, second),
            )
        finally:
            G.set_native_geometry_enabled(original)


if __name__ == "__main__":
    unittest.main()
