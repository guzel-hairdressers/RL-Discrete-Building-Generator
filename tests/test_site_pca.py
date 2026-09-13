"""Unit tests for PROP-18 Site Geometry Priors & Urban Context Orientation."""

import math
import unittest

from geometry import (
    compute_polygon_second_moments,
    compute_prevailing_context_orientation,
    get_site_orientation_prior,
)


class TestSitePCA(unittest.TestCase):
    """Test mathematical correctness and invariance of polygon second-moment PCA."""

    def test_axis_aligned_rectangle(self):
        rect = [{"x": 0.0, "y": 0.0}, {"x": 20.0, "y": 0.0}, {"x": 20.0, "y": 10.0}, {"x": 0.0, "y": 10.0}]
        res = compute_polygon_second_moments(rect)
        self.assertIsNotNone(res)
        self.assertAlmostEqual(res["area"], 200.0, places=4)
        self.assertAlmostEqual(res["centroid"][0], 10.0, places=4)
        self.assertAlmostEqual(res["centroid"][1], 5.0, places=4)
        self.assertAlmostEqual(res["aspect_ratio"], 2.0, places=4)
        self.assertAlmostEqual(res["angle_deg"], 0.0, places=4)
        self.assertAlmostEqual(res["axis_u"][0], 1.0, places=4)
        self.assertAlmostEqual(res["axis_u"][1], 0.0, places=4)

    def test_rotated_rectangle_arbitrary_angles(self):
        for angle_deg in [15.0, 30.0, 45.0, 60.0, -35.0]:
            theta = math.radians(angle_deg)
            c, s = math.cos(theta), math.sin(theta)
            base = [(0.0, 0.0), (30.0, 0.0), (30.0, 10.0), (0.0, 10.0)]
            rotated = [{"x": x * c - y * s, "y": x * s + y * c} for x, y in base]

            res = compute_polygon_second_moments(rotated)
            self.assertIsNotNone(res)
            self.assertAlmostEqual(res["aspect_ratio"], 3.0, places=3)
            # Compare angles modulo 180 degrees
            diff = (res["angle_deg"] - angle_deg + 90.0) % 180.0 - 90.0
            self.assertAlmostEqual(diff, 0.0, places=3)

    def test_square_equilateral_anisotropy(self):
        square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        res = compute_polygon_second_moments(square)
        self.assertIsNotNone(res)
        self.assertAlmostEqual(res["aspect_ratio"], 1.0, places=4)

    def test_regular_circle_approximation(self):
        # 32-sided polygon approximating a circle
        n = 32
        pts = [(10.0 * math.cos(2 * math.pi * i / n), 10.0 * math.sin(2 * math.pi * i / n)) for i in range(n)]
        res = compute_polygon_second_moments(pts)
        self.assertIsNotNone(res)
        self.assertAlmostEqual(res["aspect_ratio"], 1.0, delta=0.01)

    def test_vertex_density_invariance(self):
        # Base rectangle: 4 vertices
        rect4 = [(0.0, 0.0), (20.0, 0.0), (20.0, 10.0), (0.0, 10.0)]
        # Subdivided rectangle: 10 vertices along the same perimeter
        rect10 = [
            (0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (20.0, 0.0),
            (20.0, 5.0), (20.0, 10.0),
            (10.0, 10.0), (5.0, 10.0), (0.0, 10.0),
            (0.0, 5.0),
        ]
        res4 = compute_polygon_second_moments(rect4)
        res10 = compute_polygon_second_moments(rect10)
        self.assertAlmostEqual(res4["aspect_ratio"], res10["aspect_ratio"], places=4)
        self.assertAlmostEqual(res4["angle_deg"], res10["angle_deg"], places=4)
        self.assertAlmostEqual(res4["area"], res10["area"], places=4)

    def test_degenerate_inputs(self):
        self.assertIsNone(compute_polygon_second_moments([]))
        self.assertIsNone(compute_polygon_second_moments([(0.0, 0.0), (1.0, 1.0)]))
        # Collinear points (zero area)
        self.assertIsNone(compute_polygon_second_moments([(0.0, 0.0), (5.0, 5.0), (10.0, 10.0)]))

    def test_context_prevailing_orientation(self):
        # 3 buildings aligned along a 22.5 degree street
        target_deg = 22.5
        theta = math.radians(target_deg)
        c, s = math.cos(theta), math.sin(theta)

        buildings = []
        for offset_x, offset_y in [(0, 0), (30, 10), (60, 20)]:
            b_pts = [(0, 0), (20, 0), (20, 8), (0, 8)]
            rot_pts = [(x * c - y * s + offset_x, x * s + y * c + offset_y) for x, y in b_pts]
            buildings.append({"vertices_2d": rot_pts})

        prevailing = compute_prevailing_context_orientation(buildings)
        self.assertAlmostEqual(math.degrees(prevailing), target_deg, places=3)

    def test_get_site_orientation_prior_fallback(self):
        # 1. Elongated site (aspect 2.5) -> site_pca source
        elongated = [(0, 0), (25, 0), (25, 10), (0, 10)]
        prior1 = get_site_orientation_prior(elongated)
        self.assertEqual(prior1["source"], "site_pca")
        self.assertAlmostEqual(prior1["angle_deg"], 0.0, places=3)

        # 2. Square site with surrounding buildings at 35 degrees -> context_buildings source
        square = [(0, 0), (15, 0), (15, 15), (0, 15)]
        theta = math.radians(35.0)
        c, s = math.cos(theta), math.sin(theta)
        context_b = [
            {"vertices": [(x * c - y * s, x * s + y * c) for x, y in [(0, 0), (20, 0), (20, 8), (0, 8)]]},
            {"vertices": [(x * c - y * s + 50, x * s + y * c) for x, y in [(0, 0), (15, 0), (15, 6), (0, 6)]]},
        ]
        prior2 = get_site_orientation_prior(square, context_buildings=context_b)
        self.assertEqual(prior2["source"], "context_buildings")
        self.assertAlmostEqual(prior2["angle_deg"], 35.0, places=3)

        # 3. Square site without context buildings -> site_pca_low_anisotropy source
        prior3 = get_site_orientation_prior(square, context_buildings=None)
        self.assertEqual(prior3["source"], "site_pca_low_anisotropy")


if __name__ == "__main__":
    unittest.main()
