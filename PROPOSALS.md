# Architectural Proposals & Roadmap — RL Discrete Building Generator

`PROPOSALS.md`

This document contains the core architectural proposals and long-term design specifications for the **RL Discrete Building Generator** (Module Lab).

> [!NOTE]
> **Status Summary**:
> * **Sections 1–5 (Graph Neural Networks & Graph RL)**: Deprioritized for current release iterations.
> * **Section 6 (Model-Driven & Policy-Controlled Core Placement)**: Active implementation proposal (Phase 1 immediate, Phase 2 roadmap).

---

## 1. Graph Representation of the Floor Plan Layout

Instead of treating the floor plan as a flat 2D grid or a set of uncoupled polygons, represent the evolving floor plan as a **Dynamic Spatial Dual Graph** $\mathcal{G}_t = (\mathcal{V}_t, \mathcal{E}_t, \mathcal{F}_t)$.

```
   [ Core Module v1 ] <== (Shared Wall) ==> [ Room Module v2 ]
          ||                                       ||
     (Vertical)                                (Frontier Port)
          ||                                       ||
   [ Core Module v1' ]                       [ Open Port p1 ]
```

### A. Node Feature Matrix $\mathbf{X} \in \mathbb{R}^{|\mathcal{V}| \times d_v}$
For every placed module $v_i \in \mathcal{V}_t$:
* **Categorical & Semantic**: One-hot category (Core, Room, Corridor, Special), shape type ($k=3$ triangle, $k=4$ quad), slot ID.
* **Geometric & Spatial**: Centroid $(x_i, y_i)$, orientation $\theta_i$, area $A_i$, perimeter $P_i$, aspect ratio, vertex count $k$.
* **Performance & Exposure**: Exposed perimeter fraction $\eta_{\text{exposed}, i}$, daylight clearance distance, number of connected vs open ports.

### B. Edge Feature Tensor $\mathbf{E} \in \mathbb{R}^{|\mathcal{E}| \times d_e}$
For every physical adjacency or structural edge $(v_i, v_j) \in \mathcal{E}_t$:
* **Coincident Wall Length**: $L_{ij} = \|\text{Segment}_{ij}\|$.
* **Connection Status**: Closed boundary wall vs. open door port vs. BPE-merged partition.
* **Relative Geometry**: Distance vector $(\Delta x_{ij}, \Delta y_{ij})$ and relative orientation $\Delta \theta_{ij}$.
* **Vertical Stacking**: Inter-floor vertical core alignment edge (in multi-floor mode).

### C. Frontier Port Nodes $\mathcal{F}_t \subset \mathcal{V}_t$
Special pseudo-nodes representing active candidate placement ports along the exposed frontier of placed modules.

---

## 2. Graph Attention Mechanism (GATv2 Architecture)

Standard Graph Convolutional Networks (GCNs) average neighbor features uniformly. In architecture, however, **a core module or an adjacent structural wall exerts vastly greater influence on spatial layout than a distant room**.

We use **GATv2 (Dynamic Graph Attention Networks)** to compute anisotropic attention weights over neighboring layout modules:

$$\alpha_{ij}^{(h)} = \frac{\exp\left( \mathbf{v}_h^T \text{LeakyReLU}\left( \mathbf{W}_1^{(h)} \mathbf{h}_i + \mathbf{W}_2^{(h)} \mathbf{h}_j + \mathbf{W}_e^{(h)} \mathbf{e}_{ij} \right) \right)}{\sum_{k \in \mathcal{N}(i)} \exp\left( \mathbf{v}_h^T \text{LeakyReLU}\left( \mathbf{W}_1^{(h)} \mathbf{h}_i + \mathbf{W}_2^{(h)} \mathbf{h}_k + \mathbf{W}_e^{(h)} \mathbf{e}_{ik} \right) \right)}$$

### Multi-Head Attention Specialization
1. **Head 1 — Spatial Adjacency & Daylight**: Attends to exterior wall exposures and daylight depth.
2. **Head 2 — Core & Structural Topology**: Attends to core accessibility, corridor flow, and vertical stacking.
3. **Head 3 — BPE Merge Potential**: Identifies neighboring modules that form optimal convex shapes when merged.

---

## 3. Graph RL Policy for Placement Proposals

Instead of sampling placements over a flattened spatial grid, the policy operates directly on the graph frontier:

```
  Graph Encoder (GATv2) ===> Frontier Port Embeddings {h_p} ===> Pointer Network ===> Selected Placement (Port p*, Shape m*)
```

1. **Graph Message Passing**: Update module representations $\mathbf{h}_i^{(L)}$ after $L$ GATv2 layers.
2. **Global Graph Context Pooling**:
   $$\mathbf{h}_{\mathcal{G}} = \text{LayerNorm}\left( \text{Concat}\left( \text{MeanPool}(\{\mathbf{h}_i\}), \text{MaxPool}(\{\mathbf{h}_i\}) \right) \right)$$
3. **Graph Attention Pointer Action Selection**:
   For each active frontier port $p \in \mathcal{F}_t$ and candidate module $m \in \mathcal{M}$:
   $$\text{Logit}(p, m) = \mathbf{w}_a^T \tanh\left( \mathbf{W}_p \mathbf{h}_p + \mathbf{W}_m \mathbf{h}_m + \mathbf{W}_{\mathcal{G}} \mathbf{h}_{\mathcal{G}} \right)$$
   $$\pi(p*, m* \mid \mathcal{G}_t) = \text{Softmax}_{p \in \mathcal{F}, m \in \mathcal{M}}\left( \text{Logit}(p, m) \right)$$

---

## 4. Graph-Driven Dynamic Palette & New Shape Generation

### A. Void-Fitting Shape Generation
When the layout graph encounters an irregular, awkward spatial void surrounded by graph nodes $\{v_{i_1}, v_{i_2}, \dots, v_{i_n}\}$, the graph attention readout aggregates the local boundary geometry of the void:

$$\mathbf{h}_{\text{void}} = \sum_{j \in \text{VoidBoundary}} \alpha_j \mathbf{h}_j$$

The shape policy head takes $\mathbf{h}_{\text{void}}$ and outputs continuous/discrete shape parameters:
* Edge count $k \in \{3, 4\}$.
* Edge lengths $l_1, \dots, l_k$ tuned specifically to bridge the open graph gap.
* Internal angles $\theta_1, \dots, \theta_{k-2}$.

### B. Graph Rewriting for BPE Module Merging
When BPE (Byte Pair Encoding) merges two adjacent modules $(v_i, v_j)$, the graph performs a **Graph Rewriting Contract Operation**:
* Nodes $v_i$ and $v_j$ contract into a single composite node $v_{ij}$.
* Internal edge $e_{ij}$ is removed.
* Outer edges $\mathcal{N}(i) \cup \mathcal{N}(j)$ are rewired to $v_{ij}$, updating the graph topology dynamically.

---

## 5. Multi-Floor 3D Graph Coupling

In multi-floor optimization (`singleFloor: False`):

```
 Floor 3:  [ Room ] <---> [ Core v3 ] <---> [ Room ]
                              |  (Inter-floor Edge)
 Floor 2:  [ Room ] <---> [ Core v2 ] <---> [ Room ]
                              |  (Inter-floor Edge)
 Floor 1:  [ Room ] <---> [ Core v1 ] <---> [ Room ]
```

* Inter-floor edges connect vertical core nodes across floors $z \in \{1, \dots, N\}$.
* GATv2 passes messages vertically along core shafts, ensuring core alignment, structural stacking, and vertical utility distribution across all floors simultaneously.

---

## 6. Model-Driven & Policy-Controlled Core Placement Strategies

To prevent core placement heuristics from forcing cores into central locations that restrict subsequent building wing options, core placement transitions through two progressive architectural phases:

### Phase 1: Dynamically Determined Core Placement (Immediate Implementation)
* **Core Count Determination**: Multi-core requirement (1 vs 2 cores) is dynamically computed based on site polygon area and story count (e.g. 2 cores for sites $> 600\text{ m}^2$ or stories $\ge 6$).
* **Model-Decided Core Placement**:
  - The policy selects initial Core 1 placement $(x_1, y_1, \theta_1, \text{CoreShapeID})$ at step $t=0$ from a set of boundary-aware candidates (SDF setback distance fields, principal edge axes, and centroid anchors).
  - Core 2 is placed sequentially at step $t=k$ either **attached to the active module frontier** (ensuring 100% geometric alignment without bridge gaps) or **detached in an unbuilt wing zone**.
* **Full Geometric Control**: Position $(x,y)$, rotation angle $\theta$, and core shape variant are 100% selected by policy logits.

### Phase 2: Fully Policy-Controlled Core Generation (Roadmap Item)
* **Autonomous Core Count & Timing**: The policy network $\pi_\theta(a_t | s_t)$ decides autonomously **when** to add a core, **how many** cores to place, and **when cores are complete** (`FINISH_CORES` action).
* **State Feature Inputs**:
  - *Egress Radius Field*: Spatial distance field from any footprint point to the nearest core.
  - *Unserviced Frontier Ratio*: Percentage of valid site area beyond fire egress safety limits ($> 30\text{m}$).
  - *Core Area Penalty*: Penalizes unnecessary cores since cores consume space on all floors ($4-8$ stories).
* **Emergent Learning**: Small sites naturally learn single-core layouts, while sprawling multi-wing sites autonomously trigger attached secondary egress cores.

---

## Architectural Comparison Summary

| Component | Standard Flat Grid RL | Proposed Graph Attention RL |
| :--- | :--- | :--- |
| **State Encoding** | Flattened 1D/2D Feature Arrays | GATv2 Spatial & Topological Graph $\mathcal{G} = (\mathcal{V}, \mathcal{E})$ |
| **Placement Action** | Grid cell index sampling | Graph Pointer Network over active frontier ports $\mathcal{F}_t$ |
| **Spatial Awareness** | Fixed raster resolution ($1\text{m}$) | Exact continuous vector geometry + dynamic edge weights |
| **Core Strategy (Phase 1)** | Fixed geometric centroid | Model-selected placement/rotation across SDF setback fields |
| **Core Strategy (Phase 2)** | Fixed core count | Fully policy-controlled core count, timing, and shape variants |
| **BPE Merging** | Post-processing heuristic | Dynamic Graph Edge Contraction & Rewriting |
| **Multi-Floor Stacking**| Evaluated independently | 3D Heterogeneous Graph Message Passing |
