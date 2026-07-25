import sys
sys.path.append('/Users/ruslan_faz/Desktop/Work/Thesis/rl_v0.4')
import geometry as G
import math

# Define two polygons similar to the ones in the image and test alignment check
# Let's say we have:
# poly1 (middle) and poly2 (bottom)
# Let's check how _overlap_interval_on_first behaves.

p1 = [
    {"x": 0.0, "y": 0.0},
    {"x": 2.0, "y": 0.0},
    {"x": 2.0, "y": 1.5},
    {"x": 0.0, "y": 1.5}
]

# Case A: perfectly aligned
# Case B: shifted by some offset
p2_shifted = [
    {"x": 1.5, "y": 1.5}, # bottom-left corner of p2 touches top of p1 at x=1.5
    {"x": 3.5, "y": 1.5},
    {"x": 3.5, "y": 3.0},
    {"x": 1.5, "y": 3.0}
]

# Let's test collinearity between edge 2 of p1 (2.0, 0.0 -> 2.0, 1.5) or edge 3 (2.0, 1.5 -> 0.0, 1.5)
# and edge 0 of p2_shifted (1.5, 1.5 -> 3.5, 1.5)
edge1_start = {"x": 2.0, "y": 1.5}
edge1_end = {"x": 0.0, "y": 1.5}

edge2_start = {"x": 1.5, "y": 1.5}
edge2_end = {"x": 3.5, "y": 1.5}

collinear = G._segments_collinear(edge1_start, edge1_end, edge2_start, edge2_end)
print(f"Collinear: {collinear}")

interval = G._overlap_interval_on_first(edge1_start, edge1_end, edge2_start, edge2_end)
print(f"Interval: {interval}")

if interval:
    start, end = interval
    overlap_fraction = end - start
    print(f"Overlap fraction on first: {overlap_fraction}")
    is_full = abs(overlap_fraction - 1.0) <= 0.05
    is_half = abs(overlap_fraction - 0.5) <= 0.05
    print(f"Is full: {is_full}, Is half: {is_half}")
