# Master Project Development Roadmap — Module Lab (v0.8+)

This document defines the master development plan for the **RL-Discrete-Building-Generator** (Module Lab), featuring **Decision-Tree Branching** and **Contingency Pathways** to handle execution dependencies.

---

## 1. Master Decision-Tree Roadmap Graph

```
[Phase 1: Learning Stability (GAE + PPO Ratio Clipping)]
  │
  ├─► [Decision Node 1: Score Variance < 8.0 pts?]
  │      ├─► (YES) ──► Proceed to [Phase 2: C Optimization & Vector Batching]
  │      └─► (NO)  ──► [Contingency 1A: MCTS / Lookahead Training Rollouts]
  │                                    │
  │  ┌─────────────────────────────────┘
  ▼  ▼
[Phase 3: High-Quality Generator Convergence & Dataset Recording (D_v1)]
  │
  ▼
[Phase 4: Neural Surrogate Reward Model & PBRS]
  │
  ├─► [Decision Node 2: Surrogate Prediction Error < 5%?]
  │      ├─► (YES) ──► Proceed to [Phase 5: Iterative Self-Improving Flywheel]
  │      └─► (NO)  ──► [Contingency 4A: GNN / Spatial Transformer Surrogate]
  │                                    │
  │  ┌─────────────────────────────────┘
  ▼  ▼
[Phase 5: Iterative Self-Improving Flywheel]
  │
  ▼
[Phase 6: Spatial Action Maps & Continuous Placement Extensions]
  │
  └─► [Decision Node 3: 2D Spatial Softmax Step Time < 2.0ms?]
         ├─► (YES) ──► [Primary Release: Continuous Spatial Generator]
         └─► (NO)  ──► [Contingency 6A: Differentiable Projection / Offset Heads]
```

---

## 2. Detailed Phase Breakdown & Contingency Pathways

### Phase 1: Learning Stability & Variance Reduction
* **Target Objective**: *Model Learning Stability & Variance Reduction*
* **Status**: `[COMPLETED]`
* **Core Tasks**:
  1. **GAE Implementation**: Implement GAE ($\gamma = 0.99, \lambda = 0.95$) in `server.py` to replace crude terminal baseline subtraction. `[DONE]`
  2. **PPO Ratio Clipping**: Implement PPO Clipped Surrogate Loss ($\epsilon = 0.2$). `[DONE]`
  3. **Advantage Normalization**: Standardize advantages per minibatch. `[DONE]`
* **Target Metric**: Reduce episode score standard deviation to $< 8.0\,\text{pts}$. `[ACHIEVED]`

> 🔀 **Decision Node 1**: Check episode score variance after training episodes.
> * **Primary Branch**: Variance $< 8.0\,\text{pts}$ -> Proceeded to **Phase 2**. `[TRIGGERED]`
> * **Contingency Branch 1A (MCTS Training Rollouts)**: Not required.

---

### Phase 1B: Real-World OSM Urban Site Integration (Context Generator) [IMMEDIATE ROADMAP]
* **Target Objective**: *Real-World Urban Site Boundaries & Solar/Context Constraints*
* **Status**: `[PLANNED / IMMEDIATE ROADMAP]` (Priority: High — Next Up)
* **Core Tasks**:
  1. **Dataset Integration**: Import site boundaries and 3D context meshes from `Context Generator` (`master_urban_dataset.json` / `database/sites/site_*.json`).
  2. **Real Site Boundary Sampler**: Add real-world OSM site polygon sampler to `FloorEnvironment` in `src/server.py`.
  3. **Site Area Classification Filtering**: Filter real-world training sites by Area Tier (`XS`, `S`, `M`, `L`, `XL`).
  4. **Daylight & Shading Context Feature Signals**: Pass surrounding context building heights and shading angles into policy observation vectors.
---

### Phase 1C: BPE Vocabulary Regularization, Area Balance & Primitive Purging
* **Target Objective**: *BPE Anti-Sprawl Penalty, Area-Balanced Proposals & Uniform Utilization*
* **Status**: `[COMPLETED]`
* **Core Tasks**:
  1. **Anti-Sprawl Penalty**: Limit subshapes per merged module ($N_{\text{subshapes}} \le 4$) and reject sprawling merges (compactness $< 0.15$ or aspect ratio $> 8.5$). `[DONE]`
  2. **Primitive Purging & Vocab Penalty**: Purge fully-consumed primitive shapes from the final dictionary; penalize active vocabulary size breaches. `[DONE]`
  3. **Module Area & Subshape Variance Penalty**: Reward uniform composite room areas ($15 – 35 \text{ m}^2$) and penalize high Coefficient of Variation ($\text{CV}$) across dictionary module sizes. `[DONE]`
  4. **Uniform Module Utilization Reward**: Evaluate Shannon Entropy $H(f)$ over module placement frequencies to encourage equal utilization of active dictionary modules. `[DONE]`
* **Target Metric**: Maximize BPE vocabulary compactness while maintaining stable layout score. `[ACHIEVED]`

---

### Phase 2: Native C Optimization & Latency Reduction
* **Target Objective**: *Optimization & Throughput Scaling*
* **Status**: `[COMPLETED]`
* **Core Tasks**:
  1. **Native C SAT & Rasterizer**: Implemented native `rasterize_polygon_c` in `fast_geometry.c` scanning integer grid cells directly in C, and single-call `G.shared_overlap_pair` / `G.symmetric_segment_overlap` hot path FFI. `[DONE]`
  2. **Spatial AABB Bounding Box Rejections**: Filtered $95\%+$ of edge pairs in `find_edge_connections`, `extract_layout_graph`, and `_bounded_snap_area_tolerance` with 2D axis-aligned bounding box tests before native FFI. `[DONE]`
  3. **GIL Lock Elimination & Rotation Caching**: Replaced GIL-thrashing thread pool with direct sequential dispatch and pre-computed rotation edge metadata `_edges_meta`, achieving **$-31.2\%$ reduction in median episode wall time** ($1.453\times$ speedup). `[DONE]`
* **Target Metric**: Reduce episode wall time by $\ge 30\%$ without score regression. `[ACHIEVED: 1.453x speedup, 0.0% regression]`

---

### Phase 3: High-Quality Model Convergence & Dataset Recording
* **Target Objective**: *Data Collection & Trajectory Archiving*
* **Status**: `[COMPLETED]`
* **Core Tasks**:
  1. **Stabilized PPO Policy**: Verified stable training convergence with PPO + GAE. `[DONE]`
  2. **Dataset Recording (`D_v1`)**: Automated trajectory and layout dataset recording (`record_dataset_trajectory` writing JSONL archives). `[DONE]`
  3. **Inference Multi-Step Beam Search (PROP-11)**: Configurable multi-step lookahead candidate beam scoring (`beamSearchWidth`) in `ParallelTrainer` and `settings`. `[DONE]`
* **Target Metric**: Verified dataset recording pipeline and beam search inference functionality with unit tests. `[ACHIEVED]`

---

### Phase 4: Dense Neural Surrogate Reward Model & Potential-Based Reward Shaping (PBRS)
* **Target Objective**: *Dense Feedback & 10x Metric Evaluation Acceleration*
* **Core Tasks**:
  1. **Surrogate Model Training**: Train a lightweight Neural Network $\hat{R}_\phi(s_t)$ on `dataset_v1` to predict final layout score from partial states.
  2. **PBRS Integration**: Integrate Potential-Based Reward Shaping ($r_t = \gamma \hat{R}_\phi(s_{t+1}) - \hat{R}_\phi(s_t)$) into `server.py`.
* **Target Metric**: Reduce per-step metric calculation time to $< 0.1\,\text{ms}$.

> 🔀 **Decision Node 2**: Check surrogate prediction error on held-out validation trajectories.
> * **Primary Branch**: If mean prediction error $< 5\%$, proceed directly to **Phase 5**.
> * **Contingency Branch 4A (GNN / Spatial Transformer Architecture)**: If MLP surrogate struggles with complex non-convex site shapes, upgrade surrogate network architecture to a Graph Neural Network (GNN) operating on room-adjacency topology graphs.

---

### Phase 5: Iterative Self-Improving Flywheel
* **Target Objective**: *Autonomous Architectural Discovery*
* **Core Tasks**:
  1. Implement iterative loop: Policy $\pi_k \to$ Record Dataset $\mathcal{D}_{k+1} \to$ Retrain Ensemble Surrogate $\hat{R}_{\phi_{k+1}} \to$ Retrain Policy $\pi_{k+1}$.
  2. Integrate ground-truth terminal anchoring ($R_{\text{true}}$ on step $T$) and 3-model ensemble voting ($\mu_R - \beta \sigma_R$) to eliminate reward hacking.
* **Target Metric**: Policy autonomously discovers complex architectural patterns (courtyard wings, split-core shafts) with mean score $> 92.0\,\text{pts}$.

---

### Phase 6: Spatial Action Maps & Continuous Placement Extensions
* **Target Objective**: *Continuous Spatial Precision & Sub-Pixel Placement*
* **Core Tasks**:
  1. **Spatial Action Maps**: Implement 2D Spatial Softmax Action Maps $\mathbf{Z} \in \mathbb{R}^{H \times W \times R}$ with boolean C validity masking.
  2. **Behavioral Cloning Pre-training**: Pre-train continuous policy on `dataset_v1` to learn valid spatial placement distributions without cold-start failures.
  3. **Live PPO Fine-Tuning**: Fine-tune the continuous policy using live PPO for sub-pixel placement precision.

> 🔀 **Decision Node 3**: Check 2D Spatial Softmax step time and memory footprint.
> * **Primary Branch**: If step time $< 2.0\,\text{ms}$ and VRAM $< 2.0\,\text{GB}$, deploy Spatial Action Maps as the primary continuous placement generator.
> * **Contingency Branch 6A (Anchor Offset Sub-Pixel Heads)**: If 2D Spatial Softmax grid resolution is too memory-intensive for large sites, switch to continuous offset prediction heads $(\Delta x, \Delta y, \Delta \theta)$ anchored to discrete candidate placements.
