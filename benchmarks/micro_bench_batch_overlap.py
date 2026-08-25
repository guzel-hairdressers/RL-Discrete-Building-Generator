"""Micro-benchmark: per-pair vs batched native overlap (candidate vs placed).

Answers two questions before wiring batching into the RL hot path:
  1. Correctness — does `polygons_overlap_any_c` agree bit-for-bit with the
     per-pair `polygons_overlap` loop on the same inputs?
  2. Speedup — how much does collapsing N ctypes round-trips into one save, at
     the "nearby" sizes the candidate generator actually sees?

Usage:
    PYTHONPATH=src python3 benchmarks/micro_bench_batch_overlap.py
"""
from __future__ import annotations

import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import geometry as G  # noqa: E402


def _rect(cx: float, cy: float, w: float, h: float) -> list[dict]:
    """Axis-aligned rectangle as a CCW polygon dict list (like a room module)."""
    return [
        {"x": cx - w / 2, "y": cy - h / 2},
        {"x": cx + w / 2, "y": cy - h / 2},
        {"x": cx + w / 2, "y": cy + h / 2},
        {"x": cx - w / 2, "y": cy + h / 2},
    ]


def _lshape(cx: float, cy: float, s: float) -> list[dict]:
    """L-shaped module (6 vertices)."""
    return [
        {"x": cx, "y": cy},
        {"x": cx + s, "y": cy},
        {"x": cx + s, "y": cy + s * 0.4},
        {"x": cx + s * 0.4, "y": cy + s * 0.4},
        {"x": cx + s * 0.4, "y": cy + s},
        {"x": cx, "y": cy + s},
    ]


def make_placed(count: int, rng: random.Random) -> list[list[dict]]:
    polys = []
    for _ in range(count):
        cx = rng.uniform(-40, 40)
        cy = rng.uniform(-40, 40)
        if rng.random() < 0.7:
            polys.append(_rect(cx, cy, rng.uniform(2, 6), rng.uniform(3, 8)))
        else:
            polys.append(_lshape(cx, cy, rng.uniform(3, 6)))
    return polys


def make_candidates(count: int, rng: random.Random) -> list[list[dict]]:
    polys = []
    for _ in range(count):
        cx = rng.uniform(-40, 40)
        cy = rng.uniform(-40, 40)
        if rng.random() < 0.7:
            polys.append(_rect(cx, cy, rng.uniform(2, 6), rng.uniform(3, 8)))
        else:
            polys.append(_lshape(cx, cy, rng.uniform(3, 6)))
    return polys


def main() -> None:
    rng = random.Random(0)
    placed = make_placed(40, rng)
    candidates = make_candidates(250, rng)

    print(f"native enabled: {G.NATIVE_GEOMETRY_ENABLED}")
    if not hasattr(G._libfast_geo, "polygons_overlap_any_c"):
        print("polygons_overlap_any_c MISSING — did you rebuild the library?")
        return

    # 1. Correctness: batch vs per-pair must agree for every candidate.
    mismatches = 0
    for cand in candidates:
        per_pair = any(G.polygons_overlap(cand, p) for p in placed)
        batch = G._native_polygons_overlap_any(cand, placed)
        if per_pair != batch:
            mismatches += 1
    print(f"correctness: {len(candidates) - mismatches}/{len(candidates)} agree "
          f"({'OK' if mismatches == 0 else 'FAIL'})")

    # 2. Speedup across nearby sizes (the loop count N that batching collapses).
    print("\nnearby | per-pair us | batch us | speedup")
    for n_nearby in (1, 2, 4, 8, 16, 40):
        # Precompute per-candidate nearby subsets of the requested size.
        trials = []
        for cand in candidates:
            nearby = placed[:n_nearby]
            trials.append((cand, nearby))

        # per-pair
        t0 = time.perf_counter()
        for cand, nearby in trials:
            any(G.polygons_overlap(cand, p) for p in nearby)
        per_pair_s = time.perf_counter() - t0

        # batch
        t0 = time.perf_counter()
        for cand, nearby in trials:
            G._native_polygons_overlap_any(cand, nearby)
        batch_s = time.perf_counter() - t0

        per_pair_us = per_pair_s * 1e6 / len(trials)
        batch_us = batch_s * 1e6 / len(trials)
        speedup = per_pair_us / max(batch_us, 1e-9)
        print(f"{n_nearby:6d} | {per_pair_us:10.2f} | {batch_us:8.2f} | {speedup:6.2f}x")


if __name__ == "__main__":
    main()
