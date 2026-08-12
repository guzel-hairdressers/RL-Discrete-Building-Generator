# Comprehensive RL Architecture Proposals & Ratings

This document presents a technical analysis and relevancy rating for all Reinforcement Learning (RL) architectural proposals discussed for the **RL-Discrete-Building-Generator** (Module Lab).

---

## Executive Summary & Rating Matrix

| Proposal ID | Proposal Name | Category | Rating | Primary Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **PROP-01** | GAE & Advantage Normalization | Learning Stability | **HIGH (Essential)** | Eliminates policy gradient variance and stabilizes baseline prediction without altering environment rules. |
| **PROP-02** | Potential-Based Reward Shaping (PBRS) | Per-Step Reward | **HIGH (Recommended)** | Mathematically guarantees optimal policy $\pi^*$ preservation while providing dense step-by-step guidance. |
| **PROP-03** | Proxy / Intermediate Step Rewards | Per-Step Reward | **MEDIUM (High Risk)** | Provides fast feedback but risks greedy local optima (e.g. placing large rooms early that block future core shafts). |
| **PROP-04** | Intrinsic Curiosity / RND Exploration | Exploration | **LOW (Low Priority)** | Our problem is geometrically constrained rather than unguided mazes; standard entropy regularization is sufficient. |
| **PROP-05** | Neural Surrogate Reward Model | Dense Reward / Speed | **HIGH (Recommended)** | Accelerates step metric evaluation by $10\times$ ($\sim 0.05\,\text{ms}$) and converts sparse rewards into dense step signals. |
| **PROP-06** | Iterative Self-Improving Flywheel | Self-Improvement | **HIGH (Future Core)** | Allows policy and surrogate model to co-evolve, continually discovering higher-level architectural principles. |
| **PROP-07** | Spatial Action Maps (2D Softmax Masking) | Continuous Placement | **HIGH (Best Continuous)** | Enables continuous spatial placement while using C-based boolean validity masks to guarantee 100% collision-free actions. |
| **PROP-08** | Direct Unconstrained Continuous $(x,y,\theta)$ | Continuous Placement | **DUMB (Not Recommended)** | $>99\%$ of sampled continuous coordinates result in wall collisions or site clipping, leading to complete gradient collapse. |
| **PROP-09** | Differentiable Projection Layer | Continuous Placement | **MEDIUM (Complex)** | Projects invalid continuous coordinates to nearest valid anchor, but gradient backpropagation across non-convex boundaries is noisy. |
| **PROP-10** | Offline Bootstrapping (BC $\to$ Live PPO) | Training Bootstrapping | **HIGH (Essential for Continuous)** | Pre-trains continuous policies on recorded discrete trajectory datasets to completely avoid cold-start collision failures. |
| **PROP-11** | Multi-Step Lookahead Beam Search / MCTS | Search / Inference | **HIGH (Inference) / MEDIUM (Training)** | Explores best actions $n$ steps deep (AlphaZero/Chess style). Instant zero-shot layout quality boost during inference; provides high-quality $Q^*$ targets for training. |
| **PROP-12** | Dynamically Determined Core Placement | Core Placement | **HIGH (Phase 1 Immediate)** | Dynamically computes core count (1 vs 2) by site area/floors, but core candidate placement, rotation, and attached sequential Core 2 are 100% policy-decided. |
| **PROP-13** | Fully Policy-Controlled Core Generation | Core Placement | **HIGH (Phase 2 Roadmap)** | Gives policy total decision autonomy over core count, placement timing ($t=k$), core shape variant selection, and attached vs detached placement via egress distance field signals. |

---

## Detailed Proposals & Architectural Analyses

### PROP-01: Generalized Advantage Estimation (GAE) & Advantage Normalization
* **Concept**: Replace crude terminal return subtraction ($A = R_{\text{terminal}} - V(s_0)$) with Temporal Difference $\text{TD}(\lambda)$ errors:
  $$\delta_t = r_t + \gamma V(s_{t+1}) - V(s_t), \quad \hat{A}_t = \sum_{l=0}^{\infty} (\gamma \lambda)^l \delta_{t+l}$$
* **Rating**: **HIGH (Essential)**
* **Justification**: Currently, all steps in an episode receive the exact same terminal advantage regardless of whether a step was brilliant or catastrophic. GAE isolates step-level credit assignment, drastically reducing policy variance ($\text{Var}(\hat{A})$) and curing layout score dispersion.

---

### PROP-02: Potential-Based Reward Shaping (PBRS)
* **Concept**: Add intermediate step rewards using a state potential function $\Phi(s)$ measuring layout quality (e.g. space fill + daylight access):
  $$r_t^{\text{shaped}} = r_t^{\text{env}} + \gamma \Phi(s_{t+1}) - \Phi(s_t)$$
* **Rating**: **HIGH (Recommended)**
* **Justification**: Unlike heuristic step rewards, Ng et al. (1999) proved that PBRS **guarantees optimal policy preservation**. The agent cannot "game" or create infinite loops because any gain from $\Phi(s_{t+1})$ is canceled out upon episode completion.

---

### PROP-03: Proxy / Intermediate Heuristic Step Rewards
* **Concept**: Award unshaped step rewards for immediate area fill ($\Delta \text{Area}_t$) or daylight access.
* **Rating**: **MEDIUM (High Risk)**
* **Justification**: While easy to implement, simple proxy rewards often induce **greedy local optima**. For example, the agent learns to place large rectangular rooms early to maximize immediate area fill, inadvertently blocking future circulation core expansion and suffering massive reachability penalties at episode end.

---

### PROP-04: Intrinsic Curiosity / Exploration Rewards (RND)
* **Concept**: Add intrinsic curiosity rewards $r_t^{\text{intrinsic}} = \|\hat{f}_\theta(s_{t+1}) - f(s_{t+1})\|^2$ based on Random Network Distillation prediction error to encourage exploring rare geometric configurations.
* **Rating**: **LOW (Low Priority)**
* **Justification**: Curiosity rewards excel in sparse, unguided mazes (e.g., Montezuma's Revenge). However, procedural building layout generation is heavily constrained by strict SAT boundary checks and anchor alignments. Standard Categorical entropy regularization ($-0.01 \cdot H(\pi)$) provides cleaner exploration without introducing intrinsic reward drift.

---

### PROP-05: Neural Surrogate Reward Model
* **Concept**: Train a lightweight MLP or Graph Neural Network (GNN) $\hat{R}_\phi(s_t)$ on partial layout states to predict expected final terminal score.
* **Rating**: **HIGH (Recommended)**
* **Justification**: Running full vector SAT raycasting, BPE layout graph extraction, and reachability graph shortest paths takes time. A neural surrogate model evaluates partial states in $\sim 0.05\,\text{ms}$ on PyTorch/CUDA, accelerating training by $10\times$ and providing instantaneous dense step feedback.

---

### PROP-06: Iterative Self-Improving Surrogate Flywheel
* **Concept**: Establish a continuous learning loop:
  1. Policy $\pi_k$ generates high-scoring layout dataset $\mathcal{D}_{k+1}$.
  2. Retrain Surrogate Model $\hat{R}_{\phi_{k+1}}$ on $\mathcal{D}_{k+1}$.
  3. Retrain Policy $\pi_{k+1}$ using updated surrogate rewards.
* **Rating**: **HIGH (Future Core)**
* **Justification**: Prevents the surrogate model from becoming an intelligence bottleneck. As the RL policy discovers novel complex architectural topologies (e.g., courtyard wings, split-core shafts), the surrogate updates its understanding of high-level architectural rules. Using ensemble voting ($\mu_R - \beta \sigma_R$) prevents reward hacking.

---

### PROP-07: Spatial Action Maps (2D Softmax Masking for Continuous Placement)
* **Concept**: Output a 2D spatial feature map $\mathbf{Z} \in \mathbb{R}^{H \times W \times R}$ across site grid cells and rotation bins. Apply native C boolean validity masks $\mathbf{M} \in \{0, 1\}^{H \times W \times R}$ before spatial softmax:
  $$\mathbf{Z}^{\text{masked}}_{x,y,r} = \mathbf{Z}_{x,y,r} + (1 - \mathbf{M}_{x,y,r}) \cdot (-10^9)$$
* **Rating**: **HIGH (Best Continuous Solution)**
* **Justification**: Combines continuous spatial placement precision (sub-pixel interpolation across site coordinates) with 100% collision-free action masking. Used by DeepMind in AlphaStar for continuous map targeting.

---

### PROP-08: Direct Unconstrained Continuous $(x,y,\theta)$ Action Space
* **Concept**: Policy directly outputs continuous Gaussian coordinates $(x, y, \theta) \sim \mathcal{N}(\mu, \Sigma)$ without action masking or anchor constraints.
* **Rating**: **DUMB (Not Recommended)**
* **Justification**: In dense geometric packing, $>99\%$ of randomly sampled continuous $(x, y, \theta)$ points result in site boundary clipping or wall collisions. Without masking, the policy receives constant collision penalties, leading to vanishing policy gradients and complete learning failure.

---

### PROP-09: Differentiable Projection Layer for Continuous Actions
* **Concept**: Actor outputs unconstrained $(x,y,\theta)$, which is projected to the nearest valid geometry: $a_{\text{valid}} = \text{proj}_{\text{SiteValid}}(a)$.
* **Rating**: **MEDIUM (Complex Implementation)**
* **Justification**: While mathematically elegant, computing smooth differentiable projections across non-convex site boundaries and multi-polygon obstacles is computationally expensive and introduces non-differentiable gradient discontinuities at boundary corners.

---

### PROP-10: Offline Bootstrapping (Behavioral Cloning $\to$ Live PPO Fine-Tuning)
* **Concept**: Record a dataset of 10,000+ high-scoring layout trajectories $\mathcal{D}$ using the strong discrete generator. Pre-train a continuous policy on $\mathcal{D}$ using Behavioral Cloning (BC), then switch to live PPO fine-tuning.
* **Rating**: **HIGH (Essential for Continuous Transitions)**
* **Justification**: Completely eliminates cold-start collision failures when introducing complex or continuous action spaces. The policy starts live training already knowing valid architectural placement strategies.

---

### PROP-11: Multi-Step Lookahead Beam Search / MCTS
* **Concept**: At current state $s_t$, expand top-$K$ candidate placements $n$ steps deep using parallel environment rollouts or policy value predictions $V(s_{t+n})$, selecting the candidate that yields the highest lookahead return:
  $$\hat{Q}(s_t, a) = \max_{a_{t+1} \dots a_{t+n-1}} V_\psi\left(s_{t+n}\right)$$
* **Rating**: **HIGH (Inference) / MEDIUM (Training)**
* **Justification**: 
  * **During Inference**: Gives an instant, zero-shot quality boost to layout generations without updating neural network weights (similar to Chess/Go engine tree search).
  * **During Training**: Can generate high-precision target $Q^*$-values for training surrogate models and policy baseline updates. However, because multi-step rollouts add compute overhead ($\approx 15-30\,\text{ms}$ per search step), it is best used selectively for dataset collection or inference search rather than on every single PPO step.
