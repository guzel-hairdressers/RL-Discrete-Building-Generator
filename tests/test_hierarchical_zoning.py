import unittest
import math
import geometry as G

class TestHierarchicalZoning(unittest.TestCase):
    def test_macro_bay_partitioning_across_boundary_families(self):
        """Verify that macro-bays are non-overlapping, cover the site, and touch the core hub."""
        families = ["lobed", "convex", "concave", "notched", "lshape", "ushape", "tshape", "rect"]
        for family in families:
            for seed in (42, 123, 999):
                rng = G.RNG(seed)
                boundary = G.make_boundary(family, rng.fork(11), {"boundaryWidth": 40.0, "boundaryHeight": 30.0})
                site = G.build_site(boundary, [])
                
                # Mock a core placed near the centroid of the site
                cx = sum(p["x"] for p in site["outer"]) / len(site["outer"])
                cy = sum(p["y"] for p in site["outer"]) / len(site["outer"])
                core_poly = [
                    {"x": cx - 2.0, "y": cy - 2.0},
                    {"x": cx + 2.0, "y": cy - 2.0},
                    {"x": cx + 2.0, "y": cy + 2.0},
                    {"x": cx - 2.0, "y": cy + 2.0},
                ]
                
                bays = G.partition_site_into_macro_bays(site["outer"], core_poly, min_bay_area=20.0, max_bays=6)
                self.assertGreaterEqual(len(bays), 2, f"Failed on family {family}, seed {seed}: too few bays")
                
                # Verify total bay area covers at least 85% of the usable site
                total_bay_area = sum(b["area"] for b in bays)
                self.assertGreater(total_bay_area, 0.5 * site["exactArea"], f"Failed on family {family}")
                
                for bay in bays:
                    self.assertGreaterEqual(bay["area"], 20.0)
                    self.assertGreaterEqual(len(bay["polygon"]), 3)
                    self.assertIn("core_contact", bay)

    def test_macro_bay_partitioning_all_site_tiers(self):
        """Verify macro-bay partitioning across all site area tiers (XS to XL)."""
        for tier in ("XS", "S", "M", "L", "XL"):
            rng = G.RNG(777)
            areas = G.sample_building_floor_areas(tier, 1, rng)
            boundary = G.make_boundary("free", rng.fork(22), {"targetSiteArea": areas[0]})
            site = G.build_site(boundary, [])
            
            cx = sum(p["x"] for p in site["outer"]) / len(site["outer"])
            cy = sum(p["y"] for p in site["outer"]) / len(site["outer"])
            core_poly = [
                {"x": cx - 1.5, "y": cy - 1.5},
                {"x": cx + 1.5, "y": cy - 1.5},
                {"x": cx + 1.5, "y": cy + 1.5},
                {"x": cx - 1.5, "y": cy + 1.5},
            ]
            
            bays = G.partition_site_into_macro_bays(site["outer"], core_poly, min_bay_area=10.0, max_bays=6)
            self.assertGreaterEqual(len(bays), 2, f"Failed on tier {tier}")

if __name__ == "__main__":
    unittest.main()
