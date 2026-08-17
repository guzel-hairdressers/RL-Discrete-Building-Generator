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
* **Core Tasks**:
  1. **GAE Implementation**: Implement GAE ($\gamma = 0.99, \lambda = 0.95$) in `server.py` to replace crude terminal baseline subtraction.
  2. **PPO Ratio Clipping**: Implement PPO Clipped Surrogate Loss ($\epsilon = 0.2$).
  3. **Advantage Normalization**: Standardize advantages per minibatch.
* **Target Metric**: Reduce episode score standard deviation to $< 8.0\,\text{pts}$.

> 🔀 **Decision Node 1**: Check episode score variance after 500 training episodes.
> * **Primary Branch**: If variance $< 8.0\,\text{pts}$, proceed directly to **Phase 2**.
> * **Contingency Branch 1A (MCTS Training Rollouts)**: If variance remains high, introduce 2-step parallel MCTS rollouts during training to compute precise empirical $Q^*(s, a)$ baseline targets before updating policy weights.

---

### Phase 1B: Real-World OSM Urban Site Integration (Context Generator) [IMMEDIATE ROADMAP]
* **Target Objective**: *Real-World Urban Site Boundaries & Solar/Context Constraints*
* **Status**: `[PLANNED / IMMEDIATE ROADMAP]` (Priority: High — Pending Execution Order)
* **Core Tasks**:
  1. **Dataset Integration**: Import site boundaries and 3D context meshes from `Context Generator` (`master_urban_dataset.json` / `database/sites/site_*.json`).
  2. **Real Site Boundary Sampler**: Add real-world OSM site polygon sampler to `FloorEnvironment` in `src/server.py`.
  3. **Site Area Classification Filtering**: Filter real-world training sites by Area Tier (`XS`, `S`, `M`, `L`, `XL`).
  4. **Daylight & Shading Context Feature Signals**: Pass surrounding context building heights and shading angles into policy observation vectors.
---

### Phase 1C: BPE Vocabulary Regularization, Area Balance & Primitive Purging [IMMEDIATE ROADMAP]
* **Target Objective**: *BPE Anti-Sprawl Penalty, Area-Balanced Proposals & Uniform Utilization*
* **Status**: `[PLANNED / IMMEDIATE ROADMAP]` (Priority: High)
* **Core Tasks**:
  1. **Anti-Sprawl Penalty**: Limit subshapes per merged module ($N_{\text{subshapes}} \le 4$) and reject sprawling merges (compactness $< 0.35$ or aspect ratio $> 3.5$).
  2. **Primitive Purging & Vocab Penalty**: Purge fully-consumed primitive shapes (e.g. `s3`) from the final dictionary; penalize active vocabulary size breaches.
  3. **Module Area & Subshape Variance Penalty**: Reward uniform composite room areas ($15 – 35 \text{ m}^2$) and penalize high Coefficient of Variation ($\text{CV}$) across dictionary module sizes.
  4. **Uniform Module Utilization Reward**: Evaluate Shannon Entropy $H(f)$ over module placement frequencies to encourage equal utilization of active dictionary modules.
---

### Phase 1D: Dynamic Site Capacity, Core Scaling & Parametric Room Hop Depth (v0.8.2) [COMPLETED]
* **Target Objective**: *High Site Fill Ratio (>60%), Area-Proportional Circulation Cores & Parametric Hop Reachability*
* **Status**: `[COMPLETED]` (Released in v0.8.2)
* **Core Tasks Completed**:
  1. **Parametric Room Hop Slider (`#maxRoomHops`)**:
     - Introduced UI range slider (Min: `1`, Max: `10`, **Default: `3`**) in the control console with live WebSocket telemetry synchronization.
     - Preserves hop-blocking mechanics to keep rooms topologically tied to circulation shafts while giving users fine-grained depth control.
  2. **Area-Proportional Core Capacity**:
     - Replaced hardcoded `core_count < 2` limit with dynamic site-area capacity `_max_cores_for_site` (1 core per ~650 m² footprint area, scaling up to 8 cores on XL sites).
  3. **Remote Lobe Core Proposals in Multi-Floor Stacking**:
     - Extended `_shared_core_stack_candidates` to probe unserved clearance cells $> \text{coreSpacing}$ away from existing cores, seeding vertical circulation shafts directly into remote wings/lobes.
  4. **Non-Fatal Multi-Floor Execution**:
     - Ensured individual floors do not prematurely terminate (`done = True`) when a shared core candidate is temporarily unavailable, allowing room placements to continue uninterrupted.
* **Verified Outcomes**: Large-site fill ratio increased from $<25\%$ to $>68\%$ with multi-core building connectivity (16 cores across 4 floors on XL lobed site).

---

### Phase 2: Native C Optimization & Parallel Rollout Batching
* **Target Objective**: *Optimization & Throughput Scaling*
* **Core Tasks**:
  1. **Native C SAT Integration**: Migrate remaining Python SAT geometry routines and spatial hash lookups to `fast_geometry.c`.
  2. **Parallel Environment Vectorization**: Implement multi-threaded environment stepping (`ParallelTrainer` C extension workers).
* **Target Metric**: Achieve sub-150ms total episode time across 4–8 story layouts (10x+ speedup over v0.6 baseline).

---

### Phase 3: High-Quality Model Convergence & Dataset Recording
* **Target Objective**: *Data Collection & Trajectory Archiving*
* **Core Tasks**:
  1. Train the stabilized PPO policy until mean episode score consistently exceeds $85.0\,\text{pts}$.
  2. Record 10,000+ completed episode trajectories into an archived dataset (`dataset_v1.h5` / `jsonl`).
  3. **Inference Multi-Step Beam Search (PROP-11)**: Add optional user setting for 3-step lookahead beam search during frontend inference, enabling instant zero-shot layout quality boosts without retraining.
* **Target Metric**: Generate a verified dataset of $\ge 10,000$ high-scoring layouts.

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
