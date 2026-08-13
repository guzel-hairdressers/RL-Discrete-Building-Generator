# Historical Implementation Ledger & Lessons Learned

This document provides a comprehensive overview of all architectural approaches, experiments, and version releases implemented in the **RL-Discrete-Building-Generator** (Module Lab).

It explicitly records **what was achieved** by successful approaches and **which approaches were discarded/useless** (along with the exact conditions/reasons), so future developers and AI agents do not repeat past mistakes.

---

## 1. Successful Implementation Releases

### `v0.8.0` — Exact Multi-Floor 4–8 Story Core Shaft Optimizer *(Authoritative Root Release)*
* **Key Achievements**:
  * **$6.54\times$ Episode Speedup ($226\,\text{ms}$/episode)** over `v0.6-c` baseline ($1.48\,\text{s}$).
  * **$14.07\times$ Step Speedup ($0.81\,\text{ms}$/step)** via C-accelerated SAT polygon overlap checking (`polygons_overlap_c` in `fast_geometry.c`).
  * Multi-floor building transaction validation ensuring vertical elevator/stair shaft alignment across $4–8$ stories (`FloorEnvironment`).
  * Continuous Truncated Log-Normal site area distribution ($\mu=7.1302, \sigma=0.7075$) with 2-stage multi-floor building area sampling ($\pm 5\%$ per-floor variation).
  * Strict quad convexity constraint enforcement across placement candidate generation, custom module synthesis, and BPE shape merging.
  * BPE reuse bonus clipping ($30.0$ pts max) to prevent reward function exploitation.
  * Full real-time HTML5 Canvas visualizer and profiler suite.
  * **Phase 1-3 Implementations**:
    * **PPO Clipped Surrogate Loss & GAE**: Replaced crude terminal baseline subtraction with Generalized Advantage Estimation ($\gamma=0.99, \lambda=0.95$) and normalized advantages with clipped surrogate ratio ($\epsilon=0.2$).
    * **BPE Vocabulary Regularization**: Enforced anti-sprawl constraints ($N_{\text{subshapes}} \le 4$, compactness $\ge 0.15$, aspect ratio $\le 8.5$), primitive module purging, and Shannon entropy utilization bonus ($+2.0 \times H_{\text{norm}}$).
    * **Native C Geometry FFI Call Reduction**: Halved native FFI boundary/overlap checks in `_candidate_from_anchor` and `_validate_edge_alignment` via `G.shared_overlap_pair` and `G.symmetric_segment_overlap`.
    * **Inference Lookahead Beam Search (PROP-11)**: Enabled configurable multi-step lookahead candidate beam scoring (`beamSearchWidth`) for inference quality boosts.
    * **Dataset Trajectory Archiving (`D_v1`)**: Built automated JSONL layout trajectory recording (`record_dataset_trajectory`).

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
