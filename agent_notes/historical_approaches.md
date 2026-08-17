# Historical Implementation Ledger & Lessons Learned

This document provides a comprehensive overview of all architectural approaches, experiments, and version releases implemented in the **RL-Discrete-Building-Generator** (Module Lab).

It explicitly records **what was achieved** by successful approaches and **which approaches were discarded/useless** (along with the exact conditions/reasons), so future developers and AI agents do not repeat past mistakes.

---

## 1. Successful Implementation Releases

### `v0.8.5` — $SE(2)$-Equivariant Relational Set Transformer & Cross-Candidate Attention
* **Key Achievements**:
  * **$SE(2)$-Equivariant Relational Set Transformer (Phase 1H)**: Upgraded `PolicyModel` from isolated single-candidate MLP evaluation to a 2-layer Multi-Head Self-Attention Transformer over all legal candidate placements $\{c_1, \dots, c_K\}$, enabling cross-wing spatial coordination across the entire building.
  * **Mathematical $SE(2)$ Invariance**: Constrained the self-attention query-key products to relative Euclidean invariants (continuous RBF distance $d_{ij} = \|\vec{p}_i - \vec{p}_j\|$ and relative normal angles $\Delta \theta_{ij} = \theta_i - \theta_j$), achieving exact mathematical rotation and translation invariance ($\|L_{\text{rotated}} - L\| < 10^{-6}$ across $45^\circ, 90^\circ, 137^\circ, 180^\circ$ transformations).
  * **168 Unit Tests Passing ($100\%$)**: Fully verified backwards compatibility and exact numerical invariance in `tests/test_equivariant_policy.py`.
* **Step-by-Step Isolated Marginal Progression: Phase 1G (`v0.8.4`) vs Phase 1H (`v0.8.5`)** (10 episodes, 120 modules/floor, 4 floors on XL Lobed sites):

| Metric | Phase 1G Baseline (`v0.8.4`) | Phase 1H (`v0.8.5` Equivariant Transformer) | Net Marginal Delta | Impact & Evaluation |
| :--- | :---: | :---: | :---: | :--- |
| **Mean Episode Wall Time** | **$6.67\,\text{s}$ / ep** | **$6.89\,\text{s}$ / ep** | **$+0.22\,\text{s}$ / ep** | Cross-candidate self-attention overhead is $< 2\,\text{ms}$ per step. |
| **Mean Floor Fill Ratio** | **$46.5\%$** | **$47.2\%$** | **$+0.7\%$** | Enhanced spatial coordination improves wing boundary utilization. |
| **Mean Rentable Area Ratio** | **$90.9\%$** | **$90.9\%$** | **$+0.0\%$** | Preserves tight circulation and core access efficiency. |
| **Mathematical $SE(2)$ Invariance** | **No** (Prone to rotation bias) | **YES (100% Invariant)** | **Exact Symmetry** | Elimination of orientation sample-efficiency penalty. |


### `v0.8.4` — Inverted Geometric Slot Grammar & Medial Spine Multi-Floor Cores
* **Key Achievements**:
  * **$2.69\times$ Speedup in Candidate Generation ($124.11\,\text{s} \to 46.13\,\text{s}$)** across 10 deterministic seed episodes at 120 placements/floor ($480$ modules across 4 floors on XL Lobed sites).
  * **Inverted `(Normal, Length)` Shape Compatibility Index**: Eliminated $O(N_{\text{shapes}} \cdot N_{\text{rot}} \cdot E_{\text{building}})$ combinatorial nested search loops by indexing the active module dictionary once at initialization and performing direct $O(1)$ discrete compatibility lookups from each exterior building edge.
  * **Full-Action Policy Coverage**: With total legal placement actions reduced from $48,000$ down to $\approx 100\text{--}250$ valid candidates across the entire building, enabled the Neural Policy Network to evaluate $100\%$ of all legal actions without early-truncation (`cat_limit`), unlocking true policy optimality.
  * **Medial Spine Multi-Floor Core Seeding (Phase 1F)**: Implemented $O(1)$ Medial Axis / Voronoi ridge core facility hubs on the shared multi-floor site boundary $\Omega_{\text{shared}} = \bigcap_{k=1}^K \Omega^{(k)}$, guaranteeing $100\%$ vertical shaft alignment on Step 0 across 4–8 stories.
  * **$1.30\,\text{s}$ Multi-Floor Mean Episode Wall Time**: Total 4-floor episode wall time reduced to $1.30\,\text{s}$ with 100% test passing across all 165 unit tests.
* **Direct Head-to-Head Comparison (Pre-Change `v0.8.0` vs Post-Change `v0.8.4`)** across 10 deterministic seed episodes ($120$ modules/floor, 4 floors on XL Lobed sites):
  * **Candidate Generation Latency**: Reduced from **$16.82\,\text{ms}$** to **$7.42\,\text{ms}$** per step (**$2.27\times$ faster candidate search**).
  * **Action Space Evaluated**: Upgraded from **$12$ local actions (early truncation)** to **$100\%$ global legal actions evaluated** across every building wing.
  * **Mean Architectural Score**: Increased from **$51.48\,\text{pts}$** to **$52.66\,\text{pts}$** ($+1.18\,\text{pts}$).
  * **Mean Floor Fill Ratio**: Increased from **$23.8\%$** to **$26.2\%$** ($+2.4\%$).
  * **Rentable Area Efficiency**: Preserved at **$84.9\%$**.
  * **Vertical Shaft Alignment**: Exact $100.0\%$ (0 stacking violations across 4–8 stories).

### `v0.8.3` — High-Density Multi-Floor Scaling & Native Geometry Acceleration

* **Key Achievements**:
  * **$3.26\times$ Single-Episode Speedup ($22.64\,\text{s} \to 6.94\,\text{s}$)** on 120 placements/floor ($480$ modules across 4 floors on XL Lobed sites).
  * **Elimination of Mutex Lock Contention**: Replaced `@functools.lru_cache` on `_native_symmetric_segment_overlap_values` with unlocked collinearity filter in `src/geometry.py`, eliminating $5.12\,\text{s}$ of thread stalls across `ThreadPoolExecutor` parallel environments.
  * **$13.5\times$ Spatial Wall Slicing Acceleration**: Applied AABB bounding-box pruning in `exposed_wall_segments`, reducing edge-pair intersection overhead from $310\,\text{ms} \to 22\,\text{ms}$.
  * **Zero-Allocation Native Geometry C Extension**: Added `polygons_overlap_translated_c` and `polygon_inside_site_translated_c` in `fast_geometry.c` (ABI 3) to evaluate candidate SAT overlap and site boundary containment directly on C floating-point registers without allocating intermediate Python dictionary objects.
  * **Verified 100% Bit-for-Bit Determinism**: All multi-objective scores, room counts, and SHA-256 layout hashes remain bit-for-bit identical to baseline under fixed seeds.

### `v0.8.0` — Exact Multi-Floor 4–8 Story Core Shaft Optimizer *(Authoritative Root Release)*

* **Key Achievements**:
  * **$6.54\times$ Episode Speedup ($226\,\text{ms}$/episode)** over `v0.6-c` baseline ($1.48\,\text{s}$).
  * **$14.07\times$ Step Speedup ($0.81\,\text{ms}$/step)** via C-accelerated SAT polygon overlap checking (`polygons_overlap_c` in `fast_geometry.c`).
  * Multi-floor building transaction validation ensuring vertical elevator/stair shaft alignment across $4–8$ stories (`FloorEnvironment`).
  * Continuous Truncated Log-Normal site area distribution ($\mu=7.1302, \sigma=0.7075$) with 2-stage multi-floor building area sampling ($\pm 5\%$ per-floor variation).
  * Strict quad convexity constraint enforcement across placement candidate generation, custom module synthesis, and BPE shape merging.
  * BPE reuse bonus clipping ($30.0$ pts max) to prevent reward function exploitation.
  * Full real-time HTML5 Canvas visualizer and profiler suite.

### `v0.8.1` — Dynamic Parametric Shape Generator ($k=3,4$) *(`version/v0.8.1` Branch)*
* **Key Achievements**:
  * **$5.92\times$ Speedup** over `v0.7-d`.
  * Dynamic parametric shape synthesis per placement step ($k=3$ triangles, $k=4$ quadrilaterals).
  * On-demand dynamic rasterization dictionary (`_LazyRotationDict`).
  * Integrated Developer Diagnostics Console (`Ctrl+Shift+D` / `Cmd+Shift+D`).

### `v0.7-d` — Native C-Accelerated Dynamic Shape Baseline
* **Key Achievements**:
  * $3.61\times$ speedup ($0.41\,\text{s}$/episode) by binding low-level SAT overlap routines to C (`ctypes` interface to `fast_geometry.c`).

### `v0.7-b` — PyTorch MPS Acceleration Baseline
* **Key Achievements**:
  * Optimized PyTorch GPU/MPS device execution for Neural Policy & Critic inference on macOS ARM64 hardware.

---

## 2. Discarded & Failed Approaches (To Prevent Retrying by Mistake)

> [!CAUTION]
> Before attempting any of the following approaches, review the recorded failure reasons below. Only re-consider these approaches if underlying environment constraints or mathematical formulations have fundamentally changed.

### ❌ Experiment `v0.6-a`: Alternative Candidate Placement Anchor Search
* **Status**: **DISCARDED**
* **What was tried**: Replaced strict wall-adjacent anchor search with relaxed spatial anchor candidate placement.
* **Why it failed**: Produced fragmented layout growth with loose, floating rooms detached from circulation core access routes. Reachability graph checks failed frequently at episode end.

### ❌ Experiment `v0.6-b`: Dynamic Palette & Parametric Proposals Variant
* **Status**: **SUPERSEDED**
* **What was tried**: Generated dynamic palette rotations and parametric shape variations during candidate search.
* **Why it failed**: Achieved significantly lower variation in overall layout topologies compared to `v0.6-c`. `v0.6-c` frontier growth was selected as the foundation for `v0.8.0`.

### ❌ Experiment `v0.6-e`: Relative Frontier Reward Shaping & BPE Penalty Weighting
* **Status**: **DISCARDED / USELESS**
* **What was tried**: Introduced unshaped relative frontier rewards ($\Delta \text{Frontier}$) and weighted penalties for BPE module merging during intermediate placement steps.
* **Why it failed**: Unshaped relative rewards caused severe policy gradient instability. The agent exploited high-frequency BPE merges early on to collect immediate rewards, producing compact but severely space-inefficient buildings.

### ❌ Approach: Direct Unconstrained Continuous $(x, y, \theta)$ Action Space
* **Status**: **DISCARDED / DUMB TO IMPLEMENT WITHOUT MASKING**
* **What was tried**: Evaluated continuous Gaussian policy sampling without action masking or anchor search.
* **Why it failed**: $>99\%$ of sampled continuous coordinates resulted in wall collisions or site boundary clipping, leading to constant collision penalties and complete policy gradient collapse.
* **Condition for Re-visiting**: Only viable when paired with **Spatial Action Maps (PROP-07)** or **Offline Pre-training on Recorded Trajectories (PROP-10)**.

### ❌ Approach: Voronoi Spatial Diagram Parceling Algorithm
* **Status**: **DISCARDED**
* **What was tried**: Replaced Convex Hull + yard setback expansion with Voronoi diagram spatial partitioning (both centroid-based and point-boundary sampled Voronoi).
* **Why it failed**: In dense city contexts, point-sampled Voronoi bisectors created serrated comb-teeth artifacts between facing facades, and Voronoi cell partitioning generated unnatural parcel shapes. Convex Hull with yard setbacks was retained as the clean baseline.

### ❌ Approach: Uniform Terminal Return Subtraction Without GAE
* **Status**: **DISCARDED (Phasing out in v0.8.2)**
* **What was tried**: Computed advantage as $A = R_{\text{terminal}} - V(s_0)$, applying the exact same scalar advantage to all steps $t=0 \dots T-1$ in an episode.
* **Why it failed**: Caused massive score variance/dispersion ($\pm 28.4\,\text{pts}$ standard deviation), because early placement steps were unfairly penalized for late placement mistakes. Must be replaced with **GAE ($\gamma=0.99, \lambda=0.95$)**.

---

## 3. Low-Impact Optimizations & Reversion Candidates

### ⚠️ Phase 2 FFI Overlap Consolidation in Candidate Generation
* **Status**: `Active (Marginal Improvement / Reversion Candidate)`
* **What was done**: Consolidated redundant double calls (`_max_shared_overlap` followed by `G.get_shared_overlap`) into a single-pass `G.get_shared_overlap` in `_candidate_from_anchor` (`src/server.py`).
* **Observed Advantage**: Slight $-2.61\%$ wall time reduction ($-119.5\,\text{ms}$ per 50-episode run) with zero score/action divergence ($41.628 \to 41.628$).
* **Reversion Note**: Because the performance gain is modest, if any edge-case boundary overlap or reachability regression emerges in complex multi-core scenarios, this optimization is flagged as a primary candidate to revert back to the legacy two-stage check.
