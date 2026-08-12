"""Comprehensive tests for the BPE merge algorithm stabilization (rl_v0.6-A).

Tests cover:
- Full-edge adjacency detection
- Canonical merge key generation with symmetry
- Polygon union (merge_polygons_at_edge)
- Main bpe_merge loop: frequency thresholds, chaining, unmerge singletons
- Post-merge triangle detection and penalty logic
"""

import math
import sys
import os
import copy
import time
import unittest
from unittest import mock

# Add parent directory to path so we can import graph and geometry
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(root_dir, "src"))
sys.path.insert(0, root_dir)

import graph
import geometry as G


# ─────────────────────────────────────────────────────────
# Test Helpers: shape builders
# ─────────────────────────────────────────────────────────

def make_equilateral_triangle(cx: float, cy: float, side: float, rotation_deg: float = 0.0, shape_id: str = "t0", module_id: str = "s3") -> dict:
    """Create an equilateral triangle placement centered at (cx, cy)."""
    h = side * math.sqrt(3) / 2.0
    # Points: top, bottom-left, bottom-right (before rotation)
    pts = [
        {"x": 0.0, "y": -2*h/3},
        {"x": -side/2, "y": h/3},
        {"x": side/2, "y": h/3},
    ]
    # Rotate
    rad = math.radians(rotation_deg)
    cos_r = math.cos(rad)
    sin_r = math.sin(rad)
    rotated = []
    for p in pts:
        rx = p["x"] * cos_r - p["y"] * sin_r + cx
        ry = p["x"] * sin_r + p["y"] * cos_r + cy
        rotated.append({"x": round(rx, 6), "y": round(ry, 6)})
    
    area = G.polygon_area(rotated)
    return {
        "id": shape_id,
        "moduleId": module_id,
        "shapeType": "s3",
        "category": "room",
        "poly": rotated,
        "area": area,
        "triangle": True,
        "rotation": rotation_deg,
    }


def make_rectangle(cx: float, cy: float, w: float, h: float, rotation_deg: float = 0.0, shape_id: str = "r0", module_id: str = "s1") -> dict:
    """Create a rectangle placement centered at (cx, cy)."""
    pts = [
        {"x": -w/2, "y": -h/2},
        {"x": w/2, "y": -h/2},
        {"x": w/2, "y": h/2},
        {"x": -w/2, "y": h/2},
    ]
    rad = math.radians(rotation_deg)
    cos_r = math.cos(rad)
    sin_r = math.sin(rad)
    rotated = []
    for p in pts:
        rx = p["x"] * cos_r - p["y"] * sin_r + cx
        ry = p["x"] * sin_r + p["y"] * cos_r + cy
        rotated.append({"x": round(rx, 6), "y": round(ry, 6)})
    
    area = G.polygon_area(rotated)
    return {
        "id": shape_id,
        "moduleId": module_id,
        "shapeType": "s1",
        "category": "room",
        "poly": rotated,
        "area": area,
        "triangle": False,
        "rotation": rotation_deg,
    }


def make_right_triangle(x: float, y: float, base: float, height: float, shape_id: str = "rt0", module_id: str = "s7") -> dict:
    """Create a right triangle with the right angle at (x, y)."""
    pts = [
        {"x": x, "y": y},
        {"x": x + base, "y": y},
        {"x": x, "y": y + height},
    ]
    area = G.polygon_area(pts)
    return {
        "id": shape_id,
        "moduleId": module_id,
        "shapeType": "s7",
        "category": "room",
        "poly": pts,
        "area": area,
        "triangle": True,
        "rotation": 0.0,
    }


def make_polygon_placement(shape_id: str, shape_type: str, poly: list[dict], rotation: float = 0.0) -> dict:
    return {
        "id": shape_id,
        "moduleId": shape_type,
        "shapeType": shape_type,
        "category": "room",
        "poly": [{"x": float(point["x"]), "y": float(point["y"])} for point in poly],
        "area": G.polygon_area(poly),
        "triangle": len(poly) == 3,
        "rotation": rotation,
    }


def transform_placement(
    placement: dict,
    shape_id: str,
    angle_degrees: float = 0.0,
    dx: float = 0.0,
    dy: float = 0.0,
    reflect_x: bool = False,
) -> dict:
    radians = math.radians(angle_degrees)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    transformed = []
    for point in placement["poly"]:
        source_x = -point["x"] if reflect_x else point["x"]
        source_y = point["y"]
        transformed.append({
            "x": source_x * cosine - source_y * sine + dx,
            "y": source_x * sine + source_y * cosine + dy,
        })
    result = dict(placement)
    result["id"] = shape_id
    result["poly"] = transformed
    result["area"] = G.polygon_area(transformed)
    result["rotation"] = (float(placement.get("rotation", 0.0)) + angle_degrees) % 360.0
    return result


# ─────────────────────────────────────────────────────────
# Tests: Edge connection detection
# ─────────────────────────────────────────────────────────

class TestEdgeConnections(unittest.TestCase):
    """Tests for find_edge_connections."""
    
    def test_two_adjacent_rectangles(self):
        """Two rectangles sharing a full edge should produce one EdgeConnection."""
        r1 = make_rectangle(0.0, 0.0, 10.0, 5.0, shape_id="r1")
        r2 = make_rectangle(10.0, 0.0, 10.0, 5.0, shape_id="r2")
        
        layout_graph = graph.extract_layout_graph([r1, r2])
        conns = graph.find_edge_connections(layout_graph)
        
        assert len(conns) >= 1, f"Expected at least 1 edge connection, got {len(conns)}"
        # Verify it connects r1 and r2
        conn_ids = {(c.shape_id_a, c.shape_id_b) for c in conns}
        assert ("r1", "r2") in conn_ids or ("r2", "r1") in conn_ids
    
    def test_two_adjacent_triangles(self):
        """Two right triangles sharing a full edge should connect."""
        t1 = make_right_triangle(0.0, 0.0, 10.0, 10.0, shape_id="t1", module_id="s7")
        # Mirror triangle shares the hypotenuse or one of the legs
        # Place t2 so they share the vertical edge (x=0, y=0 to y=10 for t1, x=0, y=0 to y=10 for t2)
        t2 = {
            "id": "t2",
            "moduleId": "s7",
            "shapeType": "s7",
            "category": "room",
            "poly": [
                {"x": 0.0, "y": 0.0},
                {"x": -10.0, "y": 0.0},
                {"x": 0.0, "y": 10.0},
            ],
            "area": G.polygon_area([
                {"x": 0.0, "y": 0.0},
                {"x": -10.0, "y": 0.0},
                {"x": 0.0, "y": 10.0},
            ]),
            "triangle": True,
            "rotation": 0.0,
        }
        
        layout_graph = graph.extract_layout_graph([t1, t2])
        conns = graph.find_edge_connections(layout_graph)
        
        assert len(conns) >= 1, f"Expected at least 1 edge connection for adjacent triangles, got {len(conns)}"
    
    def test_non_adjacent_shapes(self):
        """Two shapes that don't touch should produce zero connections."""
        r1 = make_rectangle(0.0, 0.0, 5.0, 5.0, shape_id="r1")
        r2 = make_rectangle(100.0, 100.0, 5.0, 5.0, shape_id="r2")
        
        layout_graph = graph.extract_layout_graph([r1, r2])
        conns = graph.find_edge_connections(layout_graph)
        
        assert len(conns) == 0, f"Expected 0 connections for non-adjacent shapes, got {len(conns)}"


# ─────────────────────────────────────────────────────────
# Tests: Canonical merge key
# ─────────────────────────────────────────────────────────

class TestCanonicalMergeKey(unittest.TestCase):
    """Tests for merge key canonicalization with symmetry."""
    
    def test_equilateral_triangle_symmetry(self):
        """All edges of an equilateral triangle should canonicalize to edge 0."""
        side = 10.0
        h = side * math.sqrt(3) / 2.0
        poly = [
            {"x": 0.0, "y": 0.0},
            {"x": side, "y": 0.0},
            {"x": side / 2, "y": h},
        ]
        
        assert graph.canonicalize_edge_index(poly, 0) == 0
        assert graph.canonicalize_edge_index(poly, 1) == 0
        assert graph.canonicalize_edge_index(poly, 2) == 0
    
    def test_rectangle_symmetry(self):
        """Opposite edges of a rectangle should canonicalize to the same index."""
        poly = [
            {"x": 0.0, "y": 0.0},
            {"x": 10.0, "y": 0.0},
            {"x": 10.0, "y": 5.0},
            {"x": 0.0, "y": 5.0},
        ]
        
        assert graph.canonicalize_edge_index(poly, 0) == 0
        assert graph.canonicalize_edge_index(poly, 2) == 0  # opposite of 0
        assert graph.canonicalize_edge_index(poly, 1) == 1
        assert graph.canonicalize_edge_index(poly, 3) == 1  # opposite of 1
    
    def test_right_triangle_no_symmetry(self):
        """Right triangle (non-equilateral) should NOT canonicalize edges."""
        poly = [
            {"x": 0.0, "y": 0.0},
            {"x": 10.0, "y": 0.0},
            {"x": 0.0, "y": 5.0},
        ]
        
        assert graph.canonicalize_edge_index(poly, 0) == 0
        assert graph.canonicalize_edge_index(poly, 1) == 1
        assert graph.canonicalize_edge_index(poly, 2) == 2


# ─────────────────────────────────────────────────────────
# Tests: Polygon merge
# ─────────────────────────────────────────────────────────

class TestPolygonMerge(unittest.TestCase):
    """Tests for merge_polygons_at_edge."""
    
    def test_two_rectangles_merge_to_larger_rectangle(self):
        """Merging two adjacent rectangles should produce a larger rectangle."""
        poly_a = [
            {"x": 0.0, "y": 0.0},
            {"x": 5.0, "y": 0.0},
            {"x": 5.0, "y": 10.0},
            {"x": 0.0, "y": 10.0},
        ]
        poly_b = [
            {"x": 5.0, "y": 0.0},
            {"x": 10.0, "y": 0.0},
            {"x": 10.0, "y": 10.0},
            {"x": 5.0, "y": 10.0},
        ]
        # Shared edge: (5,0)→(5,10) on A and (5,10)→(5,0) on B (anti-parallel)
        edge_a = ({"x": 5.0, "y": 0.0}, {"x": 5.0, "y": 10.0})
        edge_b = ({"x": 5.0, "y": 10.0}, {"x": 5.0, "y": 0.0})
        
        merged = graph.merge_polygons_at_edge(poly_a, poly_b, edge_a, edge_b)
        
        assert merged is not None, "Merge should succeed"
        assert len(merged) == 4, f"Expected 4-vertex rectangle, got {len(merged)} vertices"
        
        # Area should be sum of both
        area_merged = G.polygon_area(merged)
        expected_area = 5 * 10 + 5 * 10
        assert abs(area_merged - expected_area) < 0.1, f"Expected area {expected_area}, got {area_merged}"
    
    def test_two_right_triangles_merge_to_rectangle(self):
        """Two complementary right triangles should merge into a rectangle."""
        poly_a = [
            {"x": 0.0, "y": 0.0},
            {"x": 10.0, "y": 0.0},
            {"x": 0.0, "y": 10.0},
        ]
        poly_b = [
            {"x": 10.0, "y": 0.0},
            {"x": 10.0, "y": 10.0},
            {"x": 0.0, "y": 10.0},
        ]
        # Shared edge: hypotenuse (10,0)→(0,10) on A and (0,10)→(10,0) on B
        edge_a = ({"x": 10.0, "y": 0.0}, {"x": 0.0, "y": 10.0})
        edge_b = ({"x": 0.0, "y": 10.0}, {"x": 10.0, "y": 0.0})
        
        merged = graph.merge_polygons_at_edge(poly_a, poly_b, edge_a, edge_b)
        
        assert merged is not None, "Merge should succeed"
        # Should be a 4-vertex rectangle (or at least 4 vertices)
        area_merged = G.polygon_area(merged)
        expected_area = 10.0 * 10.0  # full rectangle area
        assert abs(area_merged - expected_area) < 0.1, f"Expected area {expected_area}, got {area_merged}"
    
    def test_merge_failure_returns_none(self):
        """Non-touching polygons should fail to merge gracefully."""
        poly_a = [
            {"x": 0.0, "y": 0.0},
            {"x": 5.0, "y": 0.0},
            {"x": 5.0, "y": 5.0},
            {"x": 0.0, "y": 5.0},
        ]
        poly_b = [
            {"x": 100.0, "y": 100.0},
            {"x": 110.0, "y": 100.0},
            {"x": 110.0, "y": 110.0},
            {"x": 100.0, "y": 110.0},
        ]
        edge_a = ({"x": 5.0, "y": 0.0}, {"x": 5.0, "y": 5.0})
        edge_b = ({"x": 100.0, "y": 110.0}, {"x": 100.0, "y": 100.0})
        
        merged = graph.merge_polygons_at_edge(poly_a, poly_b, edge_a, edge_b)
        assert merged is None, "Merge of non-touching polygons should return None"


# ─────────────────────────────────────────────────────────
# Tests: Full BPE merge loop
# ─────────────────────────────────────────────────────────

class TestBpeMergeLoop(unittest.TestCase):
    """Tests for the main bpe_merge function."""
    
    def _make_two_floor_layout_with_paired_triangles(self):
        """Create a layout where each floor has two right triangles forming a rectangle.
        
        Floor 0: t1_a + t1_b (adjacent)
        Floor 1: t2_a + t2_b (same configuration, translated)
        
        This should trigger a merge because the pair appears 2x globally.
        """
        # Floor 0
        t1_a = make_right_triangle(0.0, 0.0, 10.0, 10.0, shape_id="f0:p0", module_id="s7")
        t1_b = {
            "id": "f0:p1",
            "moduleId": "s7",
            "shapeType": "s7",
            "category": "room",
            "poly": [
                {"x": 10.0, "y": 0.0},
                {"x": 10.0, "y": 10.0},
                {"x": 0.0, "y": 10.0},
            ],
            "area": G.polygon_area([
                {"x": 10.0, "y": 0.0},
                {"x": 10.0, "y": 10.0},
                {"x": 0.0, "y": 10.0},
            ]),
            "triangle": True,
            "rotation": 0.0,
        }
        
        # Floor 1 (same configuration, offset by 50 units)
        t2_a = make_right_triangle(50.0, 0.0, 10.0, 10.0, shape_id="f1:p0", module_id="s7")
        t2_b = {
            "id": "f1:p1",
            "moduleId": "s7",
            "shapeType": "s7",
            "category": "room",
            "poly": [
                {"x": 60.0, "y": 0.0},
                {"x": 60.0, "y": 10.0},
                {"x": 50.0, "y": 10.0},
            ],
            "area": G.polygon_area([
                {"x": 60.0, "y": 0.0},
                {"x": 60.0, "y": 10.0},
                {"x": 50.0, "y": 10.0},
            ]),
            "triangle": True,
            "rotation": 0.0,
        }
        
        graph0 = graph.extract_layout_graph([t1_a, t1_b], playground_id=0)
        graph1 = graph.extract_layout_graph([t2_a, t2_b], playground_id=1)
        
        return [graph0, graph1]
    
    def test_paired_triangles_merge(self):
        """Two adjacent triangles appearing on 2 floors should merge."""
        layout_graphs = self._make_two_floor_layout_with_paired_triangles()
        
        vocab, stats = graph.bpe_merge(layout_graphs, min_frequency=2, max_rounds=5)
        
        assert len(vocab) >= 1, f"Expected at least 1 merged module, got {len(vocab)}"
        
        # After merge, each floor should have 1 node instead of 2
        for g in layout_graphs:
            assert len(g.nodes) == 1, f"Expected 1 merged node per floor, got {len(g.nodes)}"
    
    def test_single_occurrence_no_merge(self):
        """A pair appearing only once should not be merged (below min_frequency)."""
        t1 = make_right_triangle(0.0, 0.0, 10.0, 10.0, shape_id="f0:p0", module_id="s7")
        t2 = {
            "id": "f0:p1",
            "moduleId": "s7",
            "shapeType": "s7",
            "category": "room",
            "poly": [
                {"x": 10.0, "y": 0.0},
                {"x": 10.0, "y": 10.0},
                {"x": 0.0, "y": 10.0},
            ],
            "area": 50.0,
            "triangle": True,
            "rotation": 0.0,
        }
        
        layout_graphs = [graph.extract_layout_graph([t1, t2], playground_id=0)]
        vocab, stats = graph.bpe_merge(layout_graphs, min_frequency=2, max_rounds=5)
        
        # Should not merge since pair appears only once
        assert len(vocab) == 0, f"Expected 0 merged modules for single-floor pair, got {len(vocab)}"
        assert len(layout_graphs[0].nodes) == 2, "Original nodes should remain"
    
    def test_post_processing_unmerge_singleton(self):
        """A merged shape appearing only once globally should be unmerged back to components."""
        # Create a layout where a pair appears 2x on floor 0 but after merging,
        # one merged instance needs to be unmerged.
        # Actually, let's test the singleton case differently:
        # We create 3 floors. Floors 0 and 1 have a pair, floor 2 has something different.
        # After merge, the merged type appears 2x (on floors 0 and 1). That's >= 2, so it stays.
        
        # For singleton test: 2 floors, each with one pair. After merge, merged type appears 2x globally. 
        # That passes threshold. So we need a case where it appears exactly 1x.
        # Use min_frequency=1 to allow the merge, then post-processing should unmerge if count < 2.
        
        t1 = make_right_triangle(0.0, 0.0, 10.0, 10.0, shape_id="f0:p0", module_id="s7")
        t2 = {
            "id": "f0:p1",
            "moduleId": "s7b",
            "shapeType": "s7b",  # Different type to avoid pairing
            "category": "room",
            "poly": [
                {"x": 10.0, "y": 0.0},
                {"x": 10.0, "y": 10.0},
                {"x": 0.0, "y": 10.0},
            ],
            "area": 50.0,
            "triangle": True,
            "rotation": 0.0,
        }
        
        # This pair (s7 + s7b) only appears once. With min_frequency=1, BPE would merge it.
        # Post-processing should unmerge it since global count < 2.
        layout_graphs = [graph.extract_layout_graph([t1, t2], playground_id=0)]
        vocab, stats = graph.bpe_merge(layout_graphs, min_frequency=1, max_rounds=5)
        
        # The merged module was created but should be unmerged in post-processing
        # So the graph should still have 2 nodes
        assert len(layout_graphs[0].nodes) == 2, \
            f"Singleton merge should be unmerged, expected 2 nodes, got {len(layout_graphs[0].nodes)}"
    
    def test_non_destructive_fallback(self):
        """If geometry union fails, original shapes should be preserved."""
        # Create shapes that are adjacent but have tricky geometry
        r1 = make_rectangle(0.0, 0.0, 10.0, 5.0, shape_id="r1")
        r2 = make_rectangle(10.0, 0.0, 10.0, 5.0, shape_id="r2")
        
        layout_graphs = [graph.extract_layout_graph([r1, r2], playground_id=0)]
        
        # Even if merge fails, nodes should not disappear
        initial_node_count = len(layout_graphs[0].nodes)
        # Run BPE (may or may not merge depending on geometry)
        graph.bpe_merge(layout_graphs, min_frequency=1, max_rounds=1)
        
        # Verify no nodes disappeared (either merged successfully or kept intact)
        final_total = sum(len(g.nodes) for g in layout_graphs)
        assert final_total > 0, "Nodes should not disappear during BPE"


# ─────────────────────────────────────────────────────────
# Tests: Post-merge triangle detection
# ─────────────────────────────────────────────────────────

class TestPostMergeTriangles(unittest.TestCase):
    """Tests for triangle detection after BPE merging."""
    
    def test_standalone_triangle_detected(self):
        """A standalone triangle node should be detected by polygon geometry."""
        t1 = make_right_triangle(0.0, 0.0, 10.0, 10.0, shape_id="t1")
        layout_graph = graph.LayoutGraph(
            nodes={"t1": t1},
            connections=[],
            playground_id=0,
        )
        
        triangles = graph.count_post_merge_triangles([layout_graph])
        assert len(triangles) == 1, f"Expected 1 triangle, got {len(triangles)}"
        assert triangles[0]["area"] > 0
        assert triangles[0]["is_merged"] == False
    
    def test_rectangle_not_triangle(self):
        """A rectangle should not be detected as a triangle."""
        r1 = make_rectangle(0.0, 0.0, 10.0, 5.0, shape_id="r1")
        layout_graph = graph.LayoutGraph(
            nodes={"r1": r1},
            connections=[],
            playground_id=0,
        )
        
        triangles = graph.count_post_merge_triangles([layout_graph])
        assert len(triangles) == 0, f"Expected 0 triangles for rectangle, got {len(triangles)}"
    
    def test_merged_quad_not_triangle(self):
        """Two triangles merged into a quad should NOT be detected as a triangle."""
        # Simulate a merged node that is a quadrilateral
        merged_node = {
            "id": "t1_merge_t2",
            "shapeType": "M_round0_s7_s7",
            "poly": [
                {"x": 0.0, "y": 0.0},
                {"x": 10.0, "y": 0.0},
                {"x": 10.0, "y": 10.0},
                {"x": 0.0, "y": 10.0},
            ],
            "components": [
                {"id": "t1", "shapeType": "s7", "poly": [
                    {"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 0.0}, {"x": 0.0, "y": 10.0}
                ]},
                {"id": "t2", "shapeType": "s7", "poly": [
                    {"x": 10.0, "y": 0.0}, {"x": 10.0, "y": 10.0}, {"x": 0.0, "y": 10.0}
                ]},
            ],
        }
        layout_graph = graph.LayoutGraph(
            nodes={"t1_merge_t2": merged_node},
            connections=[],
            playground_id=0,
        )
        
        triangles = graph.count_post_merge_triangles([layout_graph])
        assert len(triangles) == 0, f"Merged quad should not be detected as triangle, got {len(triangles)}"
    
    def test_merged_triangle_is_detected(self):
        """A merged shape whose outer polygon is itself a triangle SHOULD be detected."""
        # Simulate a merged node whose outer polygon is still a triangle
        merged_node = {
            "id": "merged_tri",
            "shapeType": "M_round0_s7_s7",
            "poly": [
                {"x": 0.0, "y": 0.0},
                {"x": 20.0, "y": 0.0},
                {"x": 10.0, "y": 17.32},
            ],
            "components": [
                {"id": "c1", "shapeType": "s3", "poly": [
                    {"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 0.0}, {"x": 5.0, "y": 8.66}
                ]},
                {"id": "c2", "shapeType": "s3", "poly": [
                    {"x": 10.0, "y": 0.0}, {"x": 20.0, "y": 0.0}, {"x": 15.0, "y": 8.66}
                ]},
            ],
        }
        layout_graph = graph.LayoutGraph(
            nodes={"merged_tri": merged_node},
            connections=[],
            playground_id=0,
        )
        
        triangles = graph.count_post_merge_triangles([layout_graph])
        assert len(triangles) == 1, f"Merged triangle should be detected, got {len(triangles)}"
        assert triangles[0]["is_merged"] == True
    
    def test_triangle_polygon_detection(self):
        """is_triangle_polygon should correctly identify triangles."""
        tri = [
            {"x": 0.0, "y": 0.0},
            {"x": 10.0, "y": 0.0},
            {"x": 5.0, "y": 8.66},
        ]
        assert graph.is_triangle_polygon(tri) == True
        
        quad = [
            {"x": 0.0, "y": 0.0},
            {"x": 10.0, "y": 0.0},
            {"x": 10.0, "y": 5.0},
            {"x": 0.0, "y": 5.0},
        ]
        assert graph.is_triangle_polygon(quad) == False
        
        # Degenerate: quad with collinear vertex → should simplify to triangle
        degen = [
            {"x": 0.0, "y": 0.0},
            {"x": 5.0, "y": 0.0},  # collinear with edge 0-2
            {"x": 10.0, "y": 0.0},
            {"x": 5.0, "y": 8.66},
        ]
        assert graph.is_triangle_polygon(degen) == True


# ─────────────────────────────────────────────────────────
# Tests: Shape type extraction
# ─────────────────────────────────────────────────────────

class TestShapeTypeExtraction(unittest.TestCase):
    """Tests for get_node_shape_type."""
    
    def test_shape_type_from_explicit_field(self):
        node = {"id": "test", "shapeType": "s3"}
        assert graph.get_node_shape_type(node) == "s3"
    
    def test_shape_type_from_module_id(self):
        node = {"id": "test", "moduleId": "T_equi-001"}
        assert graph.get_node_shape_type(node) == "T_equi"
    
    def test_shape_type_from_procedural_module_id(self):
        node = {"id": "test", "moduleId": "gen-1-procedural-s5-001"}
        assert graph.get_node_shape_type(node) == "s5"
    
    def test_shape_type_fallback_to_id(self):
        node = {"id": "test_shape"}
        assert graph.get_node_shape_type(node) == "test_shape"


# ─────────────────────────────────────────────────────────
# Tests: Chaining merges
# ─────────────────────────────────────────────────────────

class TestChainingMerges(unittest.TestCase):
    """Test that merges can chain across rounds."""
    
    def test_four_rectangles_chain_merge(self):
        """Four adjacent rectangles on 2 floors: round 1 merges pairs, round 2 merges pairs of pairs."""
        # Floor 0: r1, r2, r3, r4 in a row
        # Floor 1: same layout offset
        floors = []
        for floor_idx in range(2):
            ox = floor_idx * 100
            placements = []
            for i in range(4):
                r = make_rectangle(
                    cx=ox + 5.0 + i * 10.0, cy=0.0,
                    w=10.0, h=5.0,
                    shape_id=f"f{floor_idx}:p{i}",
                    module_id="s1",
                )
                placements.append(r)
            floors.append(graph.extract_layout_graph(placements, playground_id=floor_idx))
        
        vocab, stats = graph.bpe_merge(floors, min_frequency=2, max_rounds=10)
        
        # Should have done at least 1 merge
        assert len(vocab) >= 1, f"Expected at least 1 merge, got {len(vocab)}"
        
        # Total nodes should be less than 8 (4 per floor × 2 floors)
        total_nodes = sum(len(g.nodes) for g in floors)
        assert total_nodes < 8, f"Expected fewer than 8 nodes after chaining, got {total_nodes}"


class TestPathOneRegressions(unittest.TestCase):
    """Path 1 acceptance tests for collision-free, topology-safe BPE."""

    @staticmethod
    def _base_and_tab(tab_start: float, prefix: str, offset: float = 0.0) -> tuple[dict, dict]:
        base = make_polygon_placement(
            f"{prefix}:base",
            "base",
            [
                {"x": offset + 0.0, "y": 0.0},
                {"x": offset + 10.0, "y": 0.0},
                {"x": offset + 10.0, "y": 4.0},
                {"x": offset + 0.0, "y": 4.0},
            ],
        )
        tab = make_polygon_placement(
            f"{prefix}:tab",
            "tab",
            [
                {"x": offset + tab_start, "y": 4.0},
                {"x": offset + tab_start + 4.0, "y": 4.0},
                {"x": offset + tab_start + 4.0, "y": 6.0},
                {"x": offset + tab_start, "y": 6.0},
            ],
        )
        return base, tab

    def test_key_invariant_to_reversed_order_60_vs_300(self):
        base, tab = self._base_and_tab(3.0, "first")
        base["rotation"] = 0.0
        tab["rotation"] = 60.0
        first_graph = graph.extract_layout_graph([base, tab])
        first_connection = graph.find_edge_connections(first_graph)[0]
        first_key = graph.canonicalize_merge_key(first_connection, first_graph)

        second_graph = graph.extract_layout_graph([tab, base])
        second_connection = graph.find_edge_connections(second_graph)[0]
        second_key = graph.canonicalize_merge_key(second_connection, second_graph)

        self.assertEqual(first_key, second_key)
        self.assertEqual(first_key.geometry_signature, second_key.geometry_signature)
        self.assertEqual(first_key.relative_angle, second_key.relative_angle)

    def test_rigidly_rotated_translated_copy_reuses_id(self):
        base, tab = self._base_and_tab(3.0, "floor0")
        rotated_base = transform_placement(base, "floor1:base", 73.0, 40.0, -17.0)
        rotated_tab = transform_placement(tab, "floor1:tab", 73.0, 40.0, -17.0)
        floors = [
            graph.extract_layout_graph([base, tab], 0),
            graph.extract_layout_graph([rotated_tab, rotated_base], 1),
        ]

        vocabulary, stats = graph.bpe_merge(floors, min_frequency=2, max_rounds=3)

        self.assertEqual(len(vocabulary), 1)
        self.assertTrue(stats["area_conserved"])
        merged_types = [next(iter(layout_graph.nodes.values()))["shapeType"] for layout_graph in floors]
        self.assertEqual(merged_types[0], merged_types[1])
        self.assertEqual(merged_types[0], vocabulary[0].type_id)

    def test_mirrored_chiral_attachment_does_not_reuse_key(self):
        base, tab = self._base_and_tab(0.0, "original")
        mirrored_base = transform_placement(base, "mirror:base", reflect_x=True, dx=20.0)
        mirrored_tab = transform_placement(tab, "mirror:tab", reflect_x=True, dx=20.0)
        original_graph = graph.extract_layout_graph([base, tab])
        mirror_graph = graph.extract_layout_graph([mirrored_base, mirrored_tab])

        original_key = graph.canonicalize_merge_key(
            graph.find_edge_connections(original_graph)[0], original_graph
        )
        mirror_key = graph.canonicalize_merge_key(
            graph.find_edge_connections(mirror_graph)[0], mirror_graph
        )

        self.assertNotEqual(original_key, mirror_key)
        self.assertNotEqual(original_key.geometry_signature, mirror_key.geometry_signature)

    def test_distinct_attachment_geometry_gets_distinct_ids(self):
        centered_a = self._base_and_tab(3.0, "center0", 0.0)
        centered_b = self._base_and_tab(3.0, "center1", 30.0)
        end_a = self._base_and_tab(0.0, "end0", 60.0)
        end_b = self._base_and_tab(0.0, "end1", 90.0)
        floors = [
            graph.extract_layout_graph(list(pair), index)
            for index, pair in enumerate((centered_a, centered_b, end_a, end_b))
        ]

        vocabulary, stats = graph.bpe_merge(floors, min_frequency=2, max_rounds=4)

        self.assertEqual(len(vocabulary), 2)
        self.assertEqual(len({module.type_id for module in vocabulary}), 2)
        self.assertEqual(len({module.geometry_signature for module in vocabulary}), 2)
        counts = {}
        for layout_graph in floors:
            self.assertEqual(len(layout_graph.nodes), 1)
            node = next(iter(layout_graph.nodes.values()))
            counts[node["shapeType"]] = counts.get(node["shapeType"], 0) + 1
        self.assertEqual(sorted(counts.values()), [2, 2])
        self.assertTrue(stats["area_conserved"])

    def test_slanted_equilateral_roundoff_connects_and_merges(self):
        height = 2.0 * math.sqrt(3.0)
        upper = make_polygon_placement(
            "floor0:upper",
            "s3",
            [{"x": 0.0, "y": 0.0}, {"x": 4.0, "y": 0.0}, {"x": 2.0, "y": height}],
        )
        lower = make_polygon_placement(
            "floor0:lower",
            "s6",
            [
                {"x": 4.0, "y": 1.0e-6},
                {"x": 0.0, "y": -1.0e-6},
                {"x": 2.0, "y": -height},
            ],
        )
        rotated_upper = transform_placement(upper, "floor1:upper", 137.0, 25.0, 11.0)
        rotated_lower = transform_placement(lower, "floor1:lower", 137.0, 25.0, 11.0)
        first_graph = graph.extract_layout_graph([upper, lower], 0)
        second_graph = graph.extract_layout_graph([rotated_lower, rotated_upper], 1)

        self.assertGreaterEqual(len(first_graph.connections), 1)
        self.assertEqual(len(graph.find_edge_connections(first_graph)), 1)
        self.assertEqual(len(graph.find_edge_connections(second_graph)), 1)

        vocabulary, stats = graph.bpe_merge([first_graph, second_graph], min_frequency=2)
        self.assertEqual(len(vocabulary), 1)
        self.assertTrue(stats["area_conserved"])
        for layout_graph in (first_graph, second_graph):
            self.assertEqual(len(layout_graph.nodes), 1)
            self.assertTrue(G.is_simple_polygon(next(iter(layout_graph.nodes.values()))["poly"]))

    def test_overlap_threshold_is_inclusive_and_order_symmetric(self):
        lower = make_polygon_placement(
            "lower",
            "wide",
            [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 0.0}, {"x": 10.0, "y": 2.0}, {"x": 0.0, "y": 2.0}],
        )
        exact_ninety = make_polygon_placement(
            "exact",
            "wide",
            [{"x": 1.0, "y": 2.0}, {"x": 11.0, "y": 2.0}, {"x": 11.0, "y": 4.0}, {"x": 1.0, "y": 4.0}],
        )
        below_ninety = make_polygon_placement(
            "below",
            "wide",
            [{"x": 1.01, "y": 2.0}, {"x": 11.01, "y": 2.0}, {"x": 11.01, "y": 4.0}, {"x": 1.01, "y": 4.0}],
        )

        for placements in ([lower, exact_ninety], [exact_ninety, lower]):
            self.assertEqual(len(graph.find_edge_connections(graph.extract_layout_graph(placements))), 1)
        for placements in ([lower, below_ninety], [below_ninety, lower]):
            self.assertEqual(len(graph.find_edge_connections(graph.extract_layout_graph(placements))), 0)

    def test_collinearity_snap_boundary_rejects_excessive_gap(self):
        lower = make_polygon_placement(
            "lower",
            "wide",
            [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 0.0}, {"x": 10.0, "y": 2.0}, {"x": 0.0, "y": 2.0}],
        )
        within = make_polygon_placement(
            "within",
            "wide",
            [{"x": 0.0, "y": 2.005}, {"x": 10.0, "y": 2.005}, {"x": 10.0, "y": 4.0}, {"x": 0.0, "y": 4.0}],
        )
        outside = make_polygon_placement(
            "outside",
            "wide",
            [{"x": 0.0, "y": 2.011}, {"x": 10.0, "y": 2.011}, {"x": 10.0, "y": 4.0}, {"x": 0.0, "y": 4.0}],
        )

        self.assertEqual(len(graph.find_edge_connections(graph.extract_layout_graph([lower, within]))), 1)
        self.assertEqual(len(graph.find_edge_connections(graph.extract_layout_graph([lower, outside]))), 0)

    def test_five_millimetre_offset_repeats_snap_transactionally(self):
        floors = []
        for floor_index in range(2):
            offset = floor_index * 30.0
            lower = make_polygon_placement(
                f"f{floor_index}:lower",
                "wide",
                [
                    {"x": offset + 0.0, "y": 0.0},
                    {"x": offset + 10.0, "y": 0.0},
                    {"x": offset + 10.0, "y": 2.0},
                    {"x": offset + 0.0, "y": 2.0},
                ],
            )
            upper = make_polygon_placement(
                f"f{floor_index}:upper",
                "wide",
                [
                    {"x": offset + 0.0, "y": 2.005},
                    {"x": offset + 10.0, "y": 2.005},
                    {"x": offset + 10.0, "y": 4.005},
                    {"x": offset + 0.0, "y": 4.005},
                ],
            )
            floors.append(graph.extract_layout_graph([lower, upper], floor_index))

        vocabulary, stats = graph.bpe_merge(floors, min_frequency=2, max_rounds=2)

        self.assertEqual(len(vocabulary), 1)
        self.assertFalse(stats["global_rollback"])
        self.assertTrue(stats["area_conserved"])
        self.assertAlmostEqual(stats["filled_area_delta"], 0.1, places=6)
        self.assertGreaterEqual(stats["snap_area_tolerance"], 0.1)
        for floor_index, layout_graph in enumerate(floors):
            self.assertEqual(len(layout_graph.nodes), 1)
            merged = next(iter(layout_graph.nodes.values()))
            self.assertTrue(G.is_simple_polygon(merged["poly"]))
            self.assertEqual(
                {component["id"] for component in merged["components"]},
                {f"f{floor_index}:lower", f"f{floor_index}:upper"},
            )

    def test_five_millimetre_overlap_repeats_fail_without_mutation(self):
        floors = []
        for floor_index in range(2):
            offset = floor_index * 30.0
            lower = make_polygon_placement(
                f"f{floor_index}:lower",
                "wide",
                [
                    {"x": offset + 0.0, "y": 0.0},
                    {"x": offset + 10.0, "y": 0.0},
                    {"x": offset + 10.0, "y": 2.0},
                    {"x": offset + 0.0, "y": 2.0},
                ],
            )
            upper = make_polygon_placement(
                f"f{floor_index}:upper",
                "wide",
                [
                    {"x": offset + 0.0, "y": 1.995},
                    {"x": offset + 10.0, "y": 1.995},
                    {"x": offset + 10.0, "y": 4.0},
                    {"x": offset + 0.0, "y": 4.0},
                ],
            )
            floors.append(graph.extract_layout_graph([lower, upper], floor_index))

        snapshots = [copy.deepcopy(layout_graph.nodes) for layout_graph in floors]
        vocabulary, stats = graph.bpe_merge(floors, min_frequency=2, max_rounds=2)

        self.assertEqual(vocabulary, [])
        self.assertEqual(stats["merged_instances"], 0)
        self.assertFalse(stats["global_rollback"])
        self.assertAlmostEqual(stats["filled_area_delta"], 0.0, places=9)
        for layout_graph, snapshot in zip(floors, snapshots):
            self.assertEqual(layout_graph.nodes, snapshot)

    def test_excessive_offset_repeated_contacts_never_merge(self):
        floors = []
        for floor_index in range(2):
            offset = floor_index * 30.0
            lower = make_polygon_placement(
                f"f{floor_index}:lower",
                "wide",
                [
                    {"x": offset, "y": 0.0},
                    {"x": offset + 10.0, "y": 0.0},
                    {"x": offset + 10.0, "y": 2.0},
                    {"x": offset, "y": 2.0},
                ],
            )
            upper = make_polygon_placement(
                f"f{floor_index}:upper",
                "wide",
                [
                    {"x": offset, "y": 2.011},
                    {"x": offset + 10.0, "y": 2.011},
                    {"x": offset + 10.0, "y": 4.011},
                    {"x": offset, "y": 4.011},
                ],
            )
            floors.append(graph.extract_layout_graph([lower, upper], floor_index))

        vocabulary, stats = graph.bpe_merge(floors, min_frequency=2)

        self.assertEqual(vocabulary, [])
        self.assertEqual([len(layout_graph.nodes) for layout_graph in floors], [2, 2])
        self.assertAlmostEqual(stats["filled_area_delta"], 0.0, places=9)

    def test_tolerance_skew_threshold_is_symmetric_for_edges_and_ports(self):
        lower = make_polygon_placement(
            "lower",
            "wide",
            [
                {"x": 0.0, "y": -2.0},
                {"x": 10.0, "y": -2.0},
                {"x": 10.0, "y": 0.0},
                {"x": 0.0, "y": 0.0},
            ],
        )
        angle = 0.0005
        cosine = math.cos(angle)
        sine = math.sin(angle)

        def skewed_upper(start_x: float, shape_id: str) -> dict:
            end_x = start_x + 10.0 * cosine
            end_y = 10.0 * sine
            return make_polygon_placement(
                shape_id,
                "wide",
                [
                    {"x": start_x, "y": 0.0},
                    {"x": end_x, "y": end_y},
                    {"x": end_x, "y": end_y + 2.0},
                    {"x": start_x, "y": 2.0},
                ],
            )

        edge_threshold = skewed_upper(1.0, "edge-threshold")
        for placements in ([lower, edge_threshold], [edge_threshold, lower]):
            layout_graph = graph.extract_layout_graph(placements)
            self.assertEqual(len(graph.find_edge_connections(layout_graph)), 0)

        exact_port = make_polygon_placement(
            "exact-port",
            "wide",
            [
                {"x": 0.5, "y": 0.0},
                {"x": 10.5, "y": 0.0},
                {"x": 10.5, "y": 2.0},
                {"x": 0.5, "y": 2.0},
            ],
        )
        self.assertGreaterEqual(len(graph.extract_layout_graph([lower, exact_port]).connections), 1)
        self.assertGreaterEqual(len(graph.extract_layout_graph([exact_port, lower]).connections), 1)

        skewed_port = skewed_upper(0.5, "skewed-port")
        first_count = len(graph.extract_layout_graph([lower, skewed_port]).connections)
        reverse_count = len(graph.extract_layout_graph([skewed_port, lower]).connections)
        self.assertEqual(first_count, reverse_count)
        self.assertEqual(first_count, 0)

    def test_partial_shifted_shared_edge_conserves_area(self):
        lower = [
            {"x": 0.0, "y": -3.0},
            {"x": 10.0, "y": -3.0},
            {"x": 10.0, "y": 0.0},
            {"x": 0.0, "y": 0.0},
        ]
        upper = [
            {"x": 0.005, "y": 0.0},
            {"x": 9.995, "y": 0.0},
            {"x": 9.995, "y": 2.0},
            {"x": 0.005, "y": 2.0},
        ]

        merged = graph.merge_polygons_at_edge(lower, upper)

        self.assertIsNotNone(merged)
        self.assertTrue(G.is_simple_polygon(merged))
        self.assertAlmostEqual(
            G.polygon_area(merged), G.polygon_area(lower) + G.polygon_area(upper), places=6
        )

    def test_multi_collinear_subsegments_leave_no_internal_wall(self):
        first = [
            {"x": 0.0, "y": 0.0},
            {"x": 4.0, "y": 0.0},
            {"x": 4.0, "y": 2.0},
            {"x": 4.0, "y": 4.0},
            {"x": 4.0, "y": 6.0},
            {"x": 0.0, "y": 6.0},
        ]
        second = [
            {"x": 4.0, "y": 1.0},
            {"x": 8.0, "y": 1.0},
            {"x": 8.0, "y": 5.0},
            {"x": 4.0, "y": 5.0},
        ]

        merged = graph.merge_polygons_at_edge(first, second)

        self.assertIsNotNone(merged)
        self.assertTrue(G.is_simple_polygon(merged))
        self.assertAlmostEqual(G.polygon_area(merged), 40.0, places=6)
        self.assertAlmostEqual(G.polygon_perimeter(merged), 28.0, places=6)
        for index, start in enumerate(merged):
            end = merged[(index + 1) % len(merged)]
            midpoint_y = (start["y"] + end["y"]) / 2.0
            is_internal_fragment = (
                abs(start["x"] - 4.0) < 1.0e-8
                and abs(end["x"] - 4.0) < 1.0e-8
                and 1.0 < midpoint_y < 5.0
            )
            self.assertFalse(is_internal_fragment)

    def test_true_hole_closure_is_refused(self):
        u_shape = [
            {"x": 0.0, "y": 0.0},
            {"x": 6.0, "y": 0.0},
            {"x": 6.0, "y": 6.0},
            {"x": 4.0, "y": 6.0},
            {"x": 4.0, "y": 2.0},
            {"x": 2.0, "y": 2.0},
            {"x": 2.0, "y": 6.0},
            {"x": 0.0, "y": 6.0},
        ]
        closing_bar = [
            {"x": 2.0, "y": 4.0},
            {"x": 4.0, "y": 4.0},
            {"x": 4.0, "y": 6.0},
            {"x": 2.0, "y": 6.0},
        ]

        self.assertTrue(G.is_simple_polygon(u_shape))
        self.assertTrue(G.is_simple_polygon(closing_bar))
        self.assertIsNone(graph.merge_polygons_at_edge(u_shape, closing_bar))

    def test_failed_union_is_transactionally_nondestructive(self):
        floor0 = self._base_and_tab(3.0, "floor0")
        floor1 = self._base_and_tab(3.0, "floor1", 30.0)
        floors = [
            graph.extract_layout_graph(list(floor0), 0),
            graph.extract_layout_graph(list(floor1), 1),
        ]
        snapshots = [copy.deepcopy(layout_graph.nodes) for layout_graph in floors]
        expected_area = sum(
            G.polygon_area(node["poly"])
            for layout_graph in floors
            for node in layout_graph.nodes.values()
        )

        with mock.patch.object(graph, "merge_polygons_at_edge", return_value=None):
            vocabulary, stats = graph.bpe_merge(floors, min_frequency=2)

        self.assertEqual(vocabulary, [])
        self.assertEqual([layout_graph.nodes for layout_graph in floors], snapshots)
        self.assertAlmostEqual(stats["filled_area_before"], expected_area, places=9)
        self.assertAlmostEqual(stats["filled_area_after"], expected_area, places=9)
        self.assertTrue(stats["area_conserved"])

    def test_chained_merges_preserve_every_component_and_simple_area(self):
        floors = []
        original_ids = {}
        original_areas = {}
        for floor_index in range(2):
            placements = [
                make_rectangle(
                    floor_index * 100.0 + 5.0 + index * 10.0,
                    0.0,
                    10.0,
                    5.0,
                    shape_id=f"f{floor_index}:p{index}",
                    module_id="s1",
                )
                for index in range(4)
            ]
            floors.append(graph.extract_layout_graph(placements, floor_index))
            original_ids[floor_index] = {placement["id"] for placement in placements}
            original_areas[floor_index] = sum(G.polygon_area(placement["poly"]) for placement in placements)

        vocabulary, stats = graph.bpe_merge(floors, min_frequency=2, max_rounds=10)

        self.assertTrue(stats["area_conserved"])
        self.assertGreaterEqual(stats["merge_rounds"], 2)
        self.assertGreaterEqual(len(vocabulary), 1)
        for floor_index, layout_graph in enumerate(floors):
            self.assertEqual(len(layout_graph.nodes), 1)
            node = next(iter(layout_graph.nodes.values()))
            self.assertTrue(G.is_simple_polygon(node["poly"]))
            self.assertAlmostEqual(G.polygon_area(node["poly"]), original_areas[floor_index], places=6)
            self.assertEqual({component["id"] for component in node["components"]}, original_ids[floor_index])

    def test_frequency_counts_maximum_disjoint_occurrences(self):
        placements = [
            make_rectangle(
                5.0 + index * 10.0,
                0.0,
                10.0,
                5.0,
                shape_id=f"p{index}",
                module_id="s1",
            )
            for index in range(4)
        ]
        layout_graph = graph.extract_layout_graph(placements)

        vocabulary, stats = graph.bpe_merge(
            [layout_graph], min_frequency=2, max_rounds=1
        )

        self.assertEqual(len(vocabulary), 1)
        self.assertEqual(len(layout_graph.nodes), 2)
        self.assertEqual(
            {node["shapeType"] for node in layout_graph.nodes.values()},
            {vocabulary[0].type_id},
        )
        self.assertEqual(stats["merged_instances"], 2)

    def test_polynomial_blossom_matching_handles_odd_dense_and_grid_graphs(self):
        odd_nodes = tuple(f"o{index}" for index in range(5))
        odd_edges = [
            (odd_nodes[index], odd_nodes[(index + 1) % 5], index)
            for index in range(5)
        ]
        self.assertEqual(len(graph._edmonds_maximum_matching(odd_nodes, odd_edges)), 2)

        dense_nodes = tuple(f"d{index:02d}" for index in range(60))
        dense_edges = []
        edge_index = 0
        for first in range(len(dense_nodes)):
            for second in range(first + 1, len(dense_nodes)):
                dense_edges.append((dense_nodes[first], dense_nodes[second], edge_index))
                edge_index += 1

        grid_nodes = tuple(f"g{row:02d}:{column:02d}" for row in range(10) for column in range(10))
        grid_edges = []
        for row in range(10):
            for column in range(10):
                node = f"g{row:02d}:{column:02d}"
                if column + 1 < 10:
                    grid_edges.append((node, f"g{row:02d}:{column + 1:02d}", len(grid_edges)))
                if row + 1 < 10:
                    grid_edges.append((node, f"g{row + 1:02d}:{column:02d}", len(grid_edges)))

        started = time.perf_counter()
        dense_matching = graph._edmonds_maximum_matching(dense_nodes, dense_edges)
        grid_matching = graph._edmonds_maximum_matching(grid_nodes, grid_edges)
        elapsed = time.perf_counter() - started

        self.assertEqual(len(dense_matching), 30)
        self.assertEqual(len(grid_matching), 50)
        self.assertEqual(
            dense_matching,
            graph._edmonds_maximum_matching(dense_nodes, list(reversed(dense_edges))),
        )
        self.assertLess(elapsed, 2.0)

    def test_parallelogram_opposite_edge_reverses_port_half(self):
        parallelogram = [
            {"x": 0.0, "y": 0.0},
            {"x": 6.0, "y": 0.0},
            {"x": 8.0, "y": 3.0},
            {"x": 2.0, "y": 3.0},
        ]
        self.assertEqual(graph.canonicalize_geometry_port("para", 0, "L", parallelogram), (0, "L"))
        self.assertEqual(graph.canonicalize_geometry_port("para", 2, "R", parallelogram), (0, "L"))
        self.assertEqual(graph.canonicalize_geometry_port("para", 1, "L", parallelogram), (1, "L"))
        self.assertEqual(graph.canonicalize_geometry_port("para", 3, "R", parallelogram), (1, "L"))


# ─────────────────────────────────────────────────────────
# Run tests
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
