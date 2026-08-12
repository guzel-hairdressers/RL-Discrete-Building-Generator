# Module Lab — Architectural Proposals & Enhancements Register

`agent_notes/proposals.md`

This document is the master tracking log for proposed reinforcement learning algorithms, continuous spatial placement strategies, policy-driven core placement architectures, and graph neural network formulations for **Module Lab (v0.8.0 / v0.8.1)**. 

Entries are **strictly ordered by priority and status**, matching the issue-tracking structure of [`agent_notes/issues.md`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/issues.md).

---

## 1. Active & High-Priority Proposals (Essential & Immediate Focus)

### PROP-15: Real-World OSM Urban Site Boundaries (Context Generator Integration)
* **Category**: Urban Context & Real-World Site Boundaries
* **Status**: `Active / Immediate Roadmap Focus` (Priority: High)
* **Rating**: **HIGH (Immediate Focus)**
* **Concept**:
  Integrate real-world urban site boundaries and 3D surrounding context blocks extracted from OpenStreetMap (OSM) via **Context Generator** (`master_urban_dataset.json` and `database/sites/site_*.json`) directly as training and evaluation environments for the RL generator.
* **Rationale & Tradeoffs**:
  Synthetic procedural polygons (`lobed`, `lshape`, `rect`) provide controlled benchmarks, but real-world sites feature irregular property setbacks, non-orthogonal street alignments, angled property corners, and daylight/solar shading constraints from neighboring real-world buildings. Integrating Context Generator dataset sites trains policies to generalize to real-world architectural site constraints.

---

### PROP-01: Generalized Advantage Estimation (GAE) & Advantage Normalization
* **Category**: Learning Stability
* **Status**: `Immediate Priority` (Priority: High)
* **Rating**: **HIGH (Essential)**
* **Concept**:
  Replace crude terminal return subtraction ($A = R_{\text{terminal}} - V(s_0)$) with Temporal Difference $\text{TD}(\lambda)$ errors and per-batch advantage normalization ($\hat{A} = (\hat{A} - \mu_A) / (\sigma_A + 10^{-8})$):
  $$\delta_t = r_t + \gamma V(s_{t+1}) - V(s_t), \quad \hat{A}_t = \sum_{l=0}^{\infty} (\gamma \lambda)^l \delta_{t+l}$$
* **Rationale & Tradeoffs**:
  Currently, all steps in an episode receive the exact same terminal return, regardless of whether an individual step was brilliant or catastrophic. GAE isolates step-level credit assignment, drastically reducing policy gradient variance ($\text{Var}(\hat{A})$) and eliminating score dispersion across training runs.

---

### PROP-12: Dynamically Determined Core Placement (Phase 1)
* **Category**: Core Placement & Egress
* **Status**: `Active Implementation` (Priority: High)
* **Rating**: **HIGH (Immediate Focus)**
* **Concept**:
  * **Core Count Rule**: Core count requirement (1 vs 2 cores) is dynamically computed based on site polygon area and story count (e.g. 2 cores for sites $> 600\text{ m}^2$ or stories $\ge 6$).
  * **Model-Decided Candidate Anchors**: The policy selects initial Core 1 placement $(x_1, y_1, \theta_1, \text{CoreShapeID})$ at step $t=0$ from a spatial candidate pool generated via Signed Distance Fields (SDFs), principal boundary axes, and structural setback contours.
  * **Sequential Attached Core 2 Placement**: Core 2 is placed sequentially at step $t=k$, **attached to the active module frontier** (ensuring 100% geometric alignment without bridge gaps) or detached in an unbuilt wing zone.
* **Rationale & Tradeoffs**:
  Eliminates the "bridge misalignment" problem of placing two fixed distant cores early. Frontier-attached Core 2 placement guarantees zero-gap layout generation while giving the model total freedom over position, rotation $\theta$, and core shape geometry.

---

### PROP-02: Potential-Based Reward Shaping (PBRS)
* **Category**: Per-Step Reward
* **Status**: `Immediate Priority` (Priority: High)
* **Rating**: **HIGH (Recommended)**
* **Concept**:
  Add intermediate step rewards using a state potential function $\Phi(s)$ measuring layout quality (e.g. space fill + daylight access):
  $$r_t^{\text{shaped}} = r_t^{\text{env}} + \gamma \Phi(s_{t+1}) - \Phi(s_t)$$
* **Rationale & Tradeoffs**:
  Unlike heuristic step rewards, Ng et al. (1999) proved that PBRS **guarantees optimal policy preservation**. The agent cannot "game" or create infinite loops because any gain from $\Phi(s_{t+1})$ is canceled out upon episode completion.

---

### PROP-05: Neural Surrogate Reward Model
* **Category**: Dense Reward / Speed Acceleration
* **Status**: `Roadmap Item` (Priority: High)
* **Rating**: **HIGH (Recommended)**
* **Concept**:
  Train a lightweight MLP or Graph Neural Network (GNN) $\hat{R}_\phi(s_t)$ on partial layout states to predict expected final terminal score.
* **Rationale & Tradeoffs**:
  Running full vector SAT raycasting, BPE layout graph extraction, and reachability graph shortest paths takes time. A neural surrogate model evaluates partial states in $\sim 0.05\,\text{ms}$ on PyTorch/CUDA, accelerating training by $10\times$ and providing instantaneous dense step feedback.

---

### PROP-07: Spatial Action Maps (2D Softmax Masking for Continuous Placement)
* **Category**: Continuous Placement
* **Status**: `Roadmap Item` (Priority: High)
* **Rating**: **HIGH (Best Continuous Solution)**
* **Concept**:
  Output a 2D spatial feature map $\mathbf{Z} \in \mathbb{R}^{H \times W \times R}$ across site grid cells and rotation bins. Apply native C boolean validity masks $\mathbf{M} \in \{0, 1\}^{H \times W \times R}$ before spatial softmax:
  $$\mathbf{Z}^{\text{masked}}_{x,y,r} = \mathbf{Z}_{x,y,r} + (1 - \mathbf{M}_{x,y,r}) \cdot (-10^9)$$
* **Rationale & Tradeoffs**:
  Combines continuous spatial placement precision (sub-pixel interpolation across site coordinates) with 100% collision-free action masking. Used by DeepMind in AlphaStar for continuous map targeting.

---

### PROP-10: Offline Bootstrapping (Behavioral Cloning $\to$ Live PPO Fine-Tuning)
* **Category**: Training Bootstrapping
* **Status**: `Roadmap Item` (Priority: High)
* **Rating**: **HIGH (Essential for Continuous Transitions)**
* **Concept**:
  Record a dataset of 10,000+ high-scoring layout trajectories $\mathcal{D}$ using the strong discrete generator. Pre-train a continuous policy on $\mathcal{D}$ using Behavioral Cloning (BC), then switch to live PPO fine-tuning.
* **Rationale & Tradeoffs**:
  Completely eliminates cold-start collision failures when introducing complex or continuous action spaces. The policy starts live training already knowing valid architectural placement strategies.

---

### PROP-11: Multi-Step Lookahead Beam Search / MCTS
* **Category**: Search / Inference Optimization
* **Status**: `Active Development` (Priority: High)
* **Rating**: **HIGH (Inference) / MEDIUM (Training)**
* **Concept**:
  At current state $s_t$, expand top-$K$ candidate placements $n$ steps deep using parallel environment rollouts or policy value predictions $V(s_{t+n})$, selecting the candidate that yields the highest lookahead return:
  $$\hat{Q}(s_t, a) = \max_{a_{t+1} \dots a_{t+n-1}} V_\psi\left(s_{t+n}\right)$$
* **Rationale & Tradeoffs**:
  * **During Inference**: Gives an instant, zero-shot quality boost to layout generations without updating neural network weights (similar to Chess/Go engine tree search).
  * **During Training**: Can generate high-precision target $Q^*$-values for training surrogate models and policy baseline updates.

---

### PROP-13: Fully Policy-Controlled Core Generation (Phase 2)
* **Category**: Core Placement & Egress
* **Status**: `Phase 2 Roadmap Item` (Priority: High)
* **Rating**: **HIGH (Advanced Goal)**
* **Concept**:
  * **Autonomous Decision Autonomy**: The policy network $\pi_\theta(a_t | s_t)$ decides autonomously **when** to add a core, **how many** cores to place, and **when core placement is complete** (`FINISH_CORES` action).
  * **State Feature Signals**:
    - *Egress Radius Field*: Spatial distance field from any footprint point to the nearest placed core.
    - *Unserviced Frontier Ratio*: Percentage of valid site area beyond fire egress safety limits ($> 30\text{m}$).
    - *Core Area Penalty*: Penalizes unnecessary cores since cores consume space across all floors ($4-8$ stories).
* **Rationale & Tradeoffs**:
  Allows the neural policy to autonomously discover site-specific core requirements—small $300\text{ m}^2$ sites naturally learn single-core layouts, while sprawling multi-wing sites autonomously trigger attached secondary egress cores.

---

### PROP-06: Iterative Self-Improving Surrogate Flywheel
* **Category**: Self-Improvement / Co-evolution
* **Status**: `Roadmap Item` (Priority: High)
* **Rating**: **HIGH (Future Core)**
* **Concept**:
  Establish a continuous learning loop:
  1. Policy $\pi_k$ generates high-scoring layout dataset $\mathcal{D}_{k+1}$.
  2. Retrain Surrogate Model $\hat{R}_{\phi_{k+1}}$ on $\mathcal{D}_{k+1}$.
  3. Retrain Policy $\pi_{k+1}$ using updated surrogate rewards.
* **Rationale & Tradeoffs**:
  Prevents the surrogate model from becoming an intelligence bottleneck. As the RL policy discovers novel complex architectural topologies (e.g., courtyard wings, split-core shafts), the surrogate updates its understanding of high-level architectural rules.

---

## 2. Medium-Priority & Evaluation Proposals (Exploration & Complex Implementations)

### PROP-03: Proxy / Intermediate Heuristic Step Rewards
* **Category**: Per-Step Reward
* **Status**: `Under Evaluation` (Priority: Medium)
* **Rating**: **MEDIUM (High Risk)**
* **Concept**:
  Award unshaped step rewards for immediate area fill ($\Delta \text{Area}_t$) or daylight access.
* **Rationale & Tradeoffs**:
  While easy to implement, simple proxy rewards often induce **greedy local optima**. For example, the agent learns to place large rectangular rooms early to maximize immediate area fill, inadvertently blocking future circulation core expansion and suffering massive reachability penalties at episode end.

---

### PROP-09: Differentiable Projection Layer for Continuous Actions
* **Category**: Continuous Placement
* **Status**: `Under Evaluation` (Priority: Medium)
* **Rating**: **MEDIUM (Complex Implementation)**
* **Concept**:
  Actor outputs unconstrained $(x,y,\theta)$, which is projected to the nearest valid geometry: $a_{\text{valid}} = \text{proj}_{\text{SiteValid}}(a)$.
* **Rationale & Tradeoffs**:
  While mathematically elegant, computing smooth differentiable projections across non-convex site boundaries and multi-polygon obstacles is computationally expensive and introduces non-differentiable gradient discontinuities at boundary corners.

---

## 3. Deprioritized & Rejected Proposals (Evaluated & Not Recommended)

### PROP-04: Intrinsic Curiosity / Exploration Rewards (RND)
* **Category**: Exploration
* **Status**: `Deprioritized` (Priority: Low)
* **Rating**: **LOW (Low Priority)**
* **Concept**:
  Add intrinsic curiosity rewards $r_t^{\text{intrinsic}} = \|\hat{f}_\theta(s_{t+1}) - f(s_{t+1})\|^2$ based on Random Network Distillation prediction error to encourage exploring rare geometric configurations.
* **Rationale & Tradeoffs**:
  Curiosity rewards excel in sparse, unguided mazes (e.g., Montezuma's Revenge). However, procedural building layout generation is heavily constrained by strict SAT boundary checks and anchor alignments. Standard Categorical entropy regularization ($-0.01 \cdot H(\pi)$) provides cleaner exploration without introducing intrinsic reward drift.

---

### PROP-14: Dynamic Spatial Dual Graph (GATv2 Graph Neural Network & Graph RL)
* **Category**: Graph RL
* **Status**: `Deprioritized` (Priority: Low)
* **Rating**: **LOW (Deprioritized)**
* **Concept**:
  Instead of treating the floor plan as a flat 2D grid, represent the layout as a **Dynamic Spatial Dual Graph** $\mathcal{G}_t = (\mathcal{V}_t, \mathcal{E}_t, \mathcal{F}_t)$. Use GATv2 multi-head attention over module adjacencies and vertical 3D multi-floor core edges.
* **Rationale & Tradeoffs**:
  Deprioritized for current iterations in favor of vector geometry + C SAT raster acceleration. While graph representations are expressive for BPE topology, tensorized vector operations on CUDA/C-Ctypes provide significantly faster rollout speeds for reinforcement learning.

---

### PROP-08: Direct Unconstrained Continuous $(x,y,\theta)$ Action Space
* **Category**: Continuous Placement
* **Status**: `Rejected` (Priority: Dumb / Not Recommended)
* **Rating**: **DUMB (Not Recommended)**
* **Concept**:
  Policy directly outputs continuous Gaussian coordinates $(x, y, \theta) \sim \mathcal{N}(\mu, \Sigma)$ without action masking or anchor constraints.
* **Rationale & Tradeoffs**:
  In dense geometric packing, $>99\%$ of randomly sampled continuous $(x, y, \theta)$ points result in site boundary clipping or wall collisions. Without masking, the policy receives constant collision penalties, leading to vanishing policy gradients and complete learning failure.
