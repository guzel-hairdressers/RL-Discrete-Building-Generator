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

---

## 4. Proposed Future Algorithm Versions (Separate Track — Deferred, Not in Current Implementation Pass)

These three proposals define a *separate* algorithm version. They are explicitly **out of scope for the current A2C-refactor + bug-fix pass** and will be implemented (if approved) after that pass is benchmarked and stable.

### PROP-16: Graph-First Generation with Voronoi Geometry Realization
* **Category**: Graph RL / Topology-First Generation
* **Status**: `Proposed — Separate Algorithm Version (Deferred)` (Priority: High)
* **Rating**: **HIGH (Future Core)**

* **Concept** — a three-stage pipeline that separates *topology* from *geometry*:
  1. **Topology construction (RL)**. The agent builds a graph $G = (V, E)$ inside the site boundary. Vertices $V$ are abstract cells (no concrete shape yet), positioned at cell centers; edges $E$ are adjacencies (cells that touch). The agent grows the graph node/edge by node/edge, rewarded for producing **repeating patterns**.
  2. **Label assignment**. Each vertex is assigned a module label from the dictionary so as to *minimize dictionary length* (maximize module reuse) and *roughly equalize cell areas*. This is a graph coloring / tiling / compression problem — implementable as a second RL head or a deterministic optimizer.
  3. **Geometry realization**. Voronoi cells around the vertex positions produce the actual room shapes; edges that Voronoi leaves ill-defined are resolved by simple laws (orthogonalization, area balancing, snapping to principal axes — see PROP-18).

* **Rationale & Tradeoffs**:
  Decouples the *discrete* combinatorial problem (adjacency + tiling) from the *continuous* geometry problem (exact wall placement). The RL inner loop becomes pure discrete graph operations, with **no expensive SAT polygon checks per step** (the current `generate_candidates` bottleneck). "Repeating patterns" formalizes what BPE/merging is already groping toward — a real graph-grammar / tessellation objective rather than a post-hoc merge pass — and a connected, typed graph can encode hard architectural invariants (connectivity, circulation continuity) directly.

* **Implementation options**:
  - *Sequential autoregressive graph growth* (add one node/edge per step) — matches the existing step-based trainer and GAE credit assignment.
  - *One-shot graph generation* (a GNN / graph-transformer emits the whole adjacency matrix conditioned on the site) — fewer steps but harder credit assignment.
  - *Graph grammar (split-and-merge)*: start from one cell, repeatedly split cells (recursive subdivision) or merge neighbors — naturally produces hierarchical, self-similar patterns.

* **Reward for "repeating patterns" (the crux)** — candidate definitions:
  - (a) subgraph-isomorphism / automorphism counts over the growing graph,
  - (b) a compression objective (MDL / BPE merge size — reuse the existing `graph.bpe_merge`),
  - (c) symmetry detection (reflection / rotation invariance of subgraphs),
  - (d) a learned discriminator that scores "pattern-ness" adversarially.

* **Risks & open questions**:
  - Defining a tractable, differentiable-enough "pattern" reward is the hardest part.
  - Not every graph is tileable by the dictionary → needs a label-assignment *feasibility* check so the RL never produces untileable graphs.
  - Voronoi → orthogonal, buildable rooms is where the geometry work lives (orthogonalization, area balancing, snapping). Existing Voronoi-based architectural plan literature exists to lean on.
  - *Relation to PROP-14*: PROP-14 deprioritized graph RL for speed, but that was a *hybrid* graph+vector approach *inside* the fast C-SAT loop. This proposal sidesteps that by **deferring all geometry to the end**, so the graph RL itself never runs SAT checks.

### PROP-17: Typed-Cell Placement (Decouple Vertical Scope from Function; Voids as Connectivity Glue)
* **Category**: Action-Space Redesign / Architectural Invariants
* **Status**: `Proposed — Separate Algorithm Version (Deferred)` (Priority: High)
* **Rating**: **HIGH (Future Core)**

* **Concept** — replace the "core vs normal module" dichotomy with two orthogonal axes:
  - **Vertical scope** (a *placement property*, not a category): `multi-floor` (placed once, replicated on every floor with aligned anchor/rotation) vs `independent` (exists on a single floor). *Any* element may be multi-floor.
  - **Function/enclosure** (element type): `core` (vertical circulation/egress — **must** be multi-floor), `room` (habitable, enclosed — either scope), `void` (open/unenclosed interior space: atrium / courtyard / light-well / gap — the "empty" element), `balcony` (open exterior attached to a room — independent only).

* **Connectivity invariant**: elements cannot be placed *disconnected*; to express distance the model places `void` elements between them (the "ditch"). This makes "the plan is one connected component (possibly routed through voids)" a **hard constraint of the action space**, not a learned penalty — which structurally eliminates the remote-core failure mode (a core dropped in a detached wing that other floors then cannot reach). `void` is a single type doing double duty: a big central void = atrium/light-well (daylight bonus); a thin void = ditch (scores nothing). Let geometry/score sort the two rather than splitting them into separate types.

* **Type mutation**: allow a `relabel` action so the model can change an already-placed cell's type at a later step (e.g. provisional `void` → `room`, or `room` → `void`) as the plan evolves. This gives the model a reversible, incremental way to reshape topology without tearing down.

* **Rationale & Tradeoffs**:
  Conflating "stacks vertically" with "is egress" is what creates the remote-core problem; decoupling them is strictly more expressive (a multi-floor lobby/stairwell can be a `room`, not a `core`). Enforcing connectivity in the action space — with voids as the escape valve — handles the single most important architectural invariant (circulation/egress continuity) by *constraint* rather than *penalty*. Empty space becomes a first-class, *valued* element instead of a byproduct.

* **Implementation options**:
  - *Hard adjacency (frontier attachment)* + a `void` type: every new element must touch the frontier; distance is expressed via voids. Simple, fast, and unifies with the frontier/action-space speed work.
  - *Connected-component placement*: place anywhere, but only if it becomes graph-connected (directly or via voids placed in the same action). More flexible, larger action space.

* **Risks & open questions**:
  - Hard adjacency can bias toward compact blobs → mitigate with the `void` type + the pattern reward (PROP-16).
  - Void scoring is load-bearing: good voids (atrium daylight, courtyard adjacency) must be rewarded, thin "ditches" must not.
  - Multi-floor *non-core* elements spend their area on every floor (like cores) — the multi-floor vs independent decision must itself be a *learned* action with a cost signal, or it will always collapse to "independent."

### PROP-18: Principal-Axes (PCA) Orientation Prior
* **Category**: Geometry / State Representation
* **Status**: `Proposed — Technique (Deferred)` (Priority: Medium-High)
* **Rating**: **HIGH (Widely Applicable)**

* **Concept**:
  Compute the site's principal axes (PCA of the boundary polygon's vertices, or an area-weighted sample) and (a) feed the axis angle(s) + anisotropy as features to the model, and/or (b) use them to align the placement grid / candidate orientation basis.

* **Rationale & Tradeoffs**:
  Current orientation guidance is a *single random angle per episode* (`orientation_basis`, `src/server.py:5975`) with no awareness of the site's own geometry. For the very common rectangular / near-rectangular sites, the dominant axes are the rectangle's sides — and grid-aligned layouts along those axes are frequently (not always) optimal. Feeding the principal axes lets the model *learn* "grid-aligned is sometimes best" instead of either imposing a hard grid or relying on a blind random basis. The anisotropy (ratio of principal-axis lengths) is also a cheap elongation signal.

* **Implementation options**:
  - (a) extra features in `_candidate_features` / `_site_descriptor` (axis angle + anisotropy),
  - (b) a learned blend between the principal axis and the random basis,
  - (c) a full 2D spectral / Laplacian embedding of the boundary.

* **Risks & open questions**:
  PCA on the full boundary is degenerate for near-square sites (axes are ill-defined) → needs a fallback (longest-edge direction, or the existing random basis) when anisotropy is low.
