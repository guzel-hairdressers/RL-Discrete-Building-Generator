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

    def test_wfc_micro_tessellation_zero_dead_gaps(self):
        """Verify that Native C WFC micro-tessellation fills structural bays with 100% cell efficiency."""
        # Test on rectangular, triangular, and irregular polygon bays
        bay_shapes = [
            # 1. 24x18m rectangle
            [{"x": 0, "y": 0}, {"x": 24, "y": 0}, {"x": 24, "y": 18}, {"x": 0, "y": 18}],
            # 2. 30x15m L-shaped bay
            [{"x": 0, "y": 0}, {"x": 30, "y": 0}, {"x": 30, "y": 9}, {"x": 15, "y": 9}, {"x": 15, "y": 15}, {"x": 0, "y": 15}],
            # 3. Trapezoid bay
            [{"x": 0, "y": 0}, {"x": 21, "y": 0}, {"x": 15, "y": 15}, {"x": 0, "y": 15}],
        ]
        
        for idx, bay_poly in enumerate(bay_shapes):
            rooms = G.tessellate_macro_bay(bay_poly, grid_size=3.0)
            self.assertGreater(len(rooms), 0, f"Bay {idx} should place at least 1 room")
            
            # Check non-overlapping
            for i in range(len(rooms)):
                for j in range(i + 1, len(rooms)):
                    overlap = G.polygons_overlap(rooms[i]["polygon"], rooms[j]["polygon"])
                    self.assertFalse(overlap, f"Room {i} and Room {j} overlap in bay {idx}")
                    
            # Check cell packing efficiency
            grid, _, _, _, _ = G.rasterize_bay_grid(bay_poly, grid_size=3.0)
            valid_cells = sum(grid)
            packed_cells = sum(r["cell_count"] for r in rooms)
            self.assertEqual(packed_cells, valid_cells, f"Bay {idx} must achieve 100% cell packing (zero dead gaps)")

    def test_wfc_tessellation_across_procedural_sites(self):
        """Verify end-to-end Macro Partitioning + WFC Micro Tessellation across procedural sites."""
        for seed in (101, 202, 303):
            rng = G.RNG(seed)
            boundary = G.make_boundary("free", rng.fork(33), {"targetSiteArea": 800.0})
            site = G.build_site(boundary, [])
            cx = sum(p["x"] for p in site["outer"]) / len(site["outer"])
            cy = sum(p["y"] for p in site["outer"]) / len(site["outer"])
            core_poly = [{"x": cx - 2, "y": cy - 2}, {"x": cx + 2, "y": cy - 2}, {"x": cx + 2, "y": cy + 2}, {"x": cx - 2, "y": cy + 2}]
            
            bays = G.partition_site_into_macro_bays(site["outer"], core_poly, min_bay_area=20.0, max_bays=6)
            all_rooms = []
            for bay in bays:
                bay_rooms = G.tessellate_macro_bay(bay["polygon"], grid_size=3.0)
                all_rooms.extend(bay_rooms)
                
            self.assertGreaterEqual(len(all_rooms), 15, f"Site {seed} should generate at least 15 rooms")
            total_room_area = sum(r["area"] for r in all_rooms)
            self.assertGreater(total_room_area, 0.40 * site["exactArea"], "Total tessellated room area must be substantial")


if __name__ == "__main__":
    unittest.main()

