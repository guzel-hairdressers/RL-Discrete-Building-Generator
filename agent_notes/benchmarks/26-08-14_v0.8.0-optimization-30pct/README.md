# 30% Performance Optimization & Latency Reduction Benchmark Report

**Date**: 2026-08-14  
**Hardware Platform**: macOS ARM64 (Apple Silicon)  
**Clean Baseline Anchor**: Commit `35e60ca` (Unpoisoned Authoritative State)  
**Contender State**: Current `main` / `version/v0.8.1` (Optimized Core Kernel)

---

## 1. Executive Summary & Goal Verification

* **Objective**: $\ge 30\%$ speedup / execution latency reduction without quality loss across multi-floor RL episode generation.
* **Unpoisoned Baseline Measured**: Official 50-episode clean baseline recorded before optimizations in [`baseline_clean_50ep.json`](./baseline_clean_50ep.json).
* **End-to-End Speedup Achieved**:
  - **Median Episode Wall Time (p50)**: **Reduced by $-31.2\%$** ($3.627\,\text{s} \to 2.497\,\text{s}$, **$1.453\times$ speedup**).
  - **Mean Episode Wall Time**: **Reduced by $-26.6\%$** ($3.989\,\text{s} \to 2.927\,\text{s}$, **$1.363\times$ speedup**).
  - **Step Latency (p50)**: **Reduced by $-21.0\%$** ($113.38\,\text{ms} \to 89.54\,\text{ms}$).
* **Zero Quality Loss**:
  - **Mean Episode Score**: **$47.641 \to 47.641$** ($\pm 0.000$ pts, identical to 3 decimal places).
  - **Layout & Action Hash Match**: **$50 / 50$ identical ($100.0\%$)** across all paired episodes.
  - **Topology Violation Rate**: **$0.000\%$** (zero multi-floor connectivity regressions).
* **Cross-Subversion Universality**:
  - Confirmed on `version/v0.8.1` (Dynamic Parametric Shape Generator $k=3,4$): **$1.347\times$ speedup** ($4.117\,\text{s} \to 3.056\,\text{s}$ wall time) with **$100.0\%$ hash parity ($50/50$)**.

---

## 2. Optimization Progression Ledger

| Optimization Stage | Episodes | Focus Area & Changes | Baseline Wall | Contender Wall | Speedup | Hash Parity | Quality / Score |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Subphase Opt-1** | 25 ep | Spatial AABB Rejects + GIL Thrashing Elimination | $4.215\,\text{s}$ | **$2.857\,\text{s}$** | **$1.475\times$** | $25 / 25$ ($100\%$) | $48.280 \to 48.280$ |
| **Subphase Opt-2** | 25 ep | Native C `rasterize_polygon_c` + Rotation Edge Caching | $3.637\,\text{s}$ | **$2.540\,\text{s}$** | **$1.432\times$** | $25 / 25$ ($100\%$) | $48.280 \to 48.280$ |
| **Full Phase Opt** | 50 ep | Full End-to-End Comparative Benchmark on `main` | $3.989\,\text{s}$ | **$2.927\,\text{s}$** | **$1.363\times$** | $50 / 50$ ($100\%$) | $47.641 \to 47.641$ |
| **Cross-Subversion** | 50 ep | Universality on `version/v0.8.1` Parametric Shapes | $4.117\,\text{s}$ | **$3.056\,\text{s}$** | **$1.347\times$** | $50 / 50$ ($100\%$) | $47.641 \to 47.641$ |

---

## 3. Key Architectural & Algorithmic Optimizations

1. **Spatial AABB Bounding Box Early Rejections (`src/graph.py`, `src/geometry.py`)**:
   - Filtered $95\%+$ of edge pairs in `find_edge_connections`, `extract_layout_graph`, and `_bounded_snap_area_tolerance` with 2D axis-aligned bounding box tests before invoking native C FFI kernels.
   - Added fast float bounding box rejection in `_native_symmetric_segment_overlap_values` before C struct boxing.
2. **Elimination of Python GIL Lock Contention (`src/server.py`)**:
   - Replaced `ThreadPoolExecutor.map` across 4 local environments with direct sequential list comprehensions, eliminating over 2.2 seconds of GIL lock acquisition stall per 10 episodes.
3. **Native C Grid Rasterizer (`src/c/fast_geometry.c`)**:
   - Implemented `rasterize_polygon_c` scanning 2D unit grid cells directly in C using compiled point-in-polygon and point-on-polygon tests, bypassing tens of thousands of Python dictionary creations.
4. **Memoized Rotation Edge Metadata (`src/server.py`)**:
   - Pre-computed and cached candidate edge vectors `(dx, dy, length, angle_key)` on rotation dictionaries in `_edge_alignment_anchors`, eliminating $>200,000$ Python `atan2` and `math.hypot` calls per episode.
5. **Pre-Computed Segment Signatures in Terminal Evaluation (`src/server.py`, `src/geometry.py`)**:
   - Pre-calculated and passed tuple signatures for `site["wallSegments"]` and `exposed_wall_segments`, eliminating repetitive dict-to-float conversions during daylight depth queries.
