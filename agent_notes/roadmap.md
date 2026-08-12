# Project Development Roadmap — Module Lab (v0.8+)

This document defines the step-by-step master development plan for the **RL-Discrete-Building-Generator** (Module Lab).

---

## Strategic Roadmap Dependency Graph

```
Phase 1: Learning Stability (GAE + PPO Clipping)
  └─► Cures score dispersion and stabilizes baseline
        │
        ▼
Phase 2: Engine Optimization & Parallel C Batching
  └─► Achieves ultra-fast rollout throughput (<150ms / episode)
        │
        ▼
Phase 3: High-Quality Generator Convergence & Dataset Recording
  └─► Generates 10,000+ high-scoring trajectory dataset D_v1
        │
        ▼
Phase 4: Neural Surrogate Reward Model & PBRS
  └─► Provides 10x metric speedup & dense step-by-step guidance
        │
        ▼
Phase 5: Iterative Self-Improving Surrogate Flywheel
  └─► Co-evolves policy & surrogate for complex architectural topologies
        │
        ▼
Phase 6: Spatial Action Maps & Continuous Placement Extensions
  └─► Pre-trains continuous policy via BC on D_v1, fine-tunes with live PPO
```

---

## Detailed Step-by-Step Milestones

### Phase 1: Learning Stability & Variance Reduction
* **Target Objective**: *Model Learning Stability & Variance Reduction*
* **Core Tasks**:
  1. **Generalized Advantage Estimation (GAE)**: Implement GAE ($\gamma = 0.99, \lambda = 0.95$) in `server.py` to replace crude terminal baseline subtraction.
  2. **PPO Ratio Clipping**: Implement PPO Clipped Surrogate Loss ($\epsilon = 0.2$) to prevent catastrophic policy updates.
  3. **Advantage Normalization**: Standardize advantages per minibatch ($\hat{A} \leftarrow (\hat{A} - \mu) / (\sigma + 10^{-8})$).
* **Target Metric**: Reduce episode score standard deviation from $\pm 28.4\,\text{pts}$ down to $< 8.0\,\text{pts}$.

---

### Phase 2: Native C Optimization & Parallel Rollout Batching
* **Target Objective**: *Optimization & Throughput Scaling*
* **Core Tasks**:
  1. **Native C SAT Integration**: Migrate remaining Python SAT geometry routines and spatial hash lookups to `fast_geometry.c`.
  2. **Parallel Environment Vectorization**: Implement multi-threaded environment stepping (`ParallelTrainer` C extension workers).
* **Target Metric**: Achieve sub-150ms total episode time across 4–8 story layouts (10x+ speedup over v0.6 baseline).

---

### Phase 3: High-Quality Model Convergence & Trajectory Recording
* **Target Objective**: *Data Collection & Trajectory Archiving*
* **Core Tasks**:
  1. Train the stabilized PPO policy until mean episode score consistently exceeds $85.0\,\text{pts}$.
  2. Record 10,000+ completed episode trajectories into an archived dataset (`dataset_v1.h5` / `jsonl`), capturing:
     * Full state history $s_0, s_1, \dots, s_T$
     * Placed module geometry & anchor choices $a_t$
     * Ground-truth terminal sub-scores (daylight, fill ratio, reachability, BPE reuse).
* **Target Metric**: Generate a verified dataset of $\ge 10,000$ high-scoring layouts for downstream surrogate model training.

---

### Phase 4: Dense Neural Surrogate Reward Model & Potential-Based Reward Shaping (PBRS)
* **Target Objective**: *Dense Feedback & 10x Metric Evaluation Acceleration*
* **Core Tasks**:
  1. **Surrogate Model Training**: Train a Graph Neural Network / MLP $\hat{R}_\phi(s_t)$ on `dataset_v1` to predict final layout score from partial states.
  2. **PBRS Integration**: Integrate Potential-Based Reward Shaping ($r_t = \gamma \hat{R}_\phi(s_{t+1}) - \hat{R}_\phi(s_t)$) into `server.py`.
* **Target Metric**: Reduce per-step metric calculation time to $< 0.1\,\text{ms}$ while providing instant intermediate step guidance.

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
* **Target Metric**: Continuous placement model achieves 100% boundary compliance with superior room proportion flexibility.
