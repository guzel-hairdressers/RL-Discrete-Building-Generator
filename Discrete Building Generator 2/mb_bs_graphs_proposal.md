# Graph Neural Networks & Graph RL Proposals for Discrete Building Generator

`mb_bs_graphs_proposal.md`

This document details the architectural proposal for incorporating **Graph Neural Networks (GNNs)**, **Graph Attention Mechanisms (GAT / GATv2)**, and **Graph Reinforcement Learning (Graph RL)** into the parallel floor-plan placement and shape generation pipeline.

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

## Architectural Comparison Summary

| Component | Standard Flat Grid RL | Proposed Graph Attention RL |
| :--- | :--- | :--- |
| **State Encoding** | Flattened 1D/2D Feature Arrays | GATv2 Spatial & Topological Graph $\mathcal{G} = (\mathcal{V}, \mathcal{E})$ |
| **Placement Action** | Grid cell index sampling | Graph Pointer Network over active frontier ports $\mathcal{F}_t$ |
| **Spatial Awareness** | Fixed raster resolution ($1\text{m}$) | Exact continuous vector geometry + dynamic edge weights |
| **BPE Merging** | Post-processing heuristic | Dynamic Graph Edge Contraction & Rewriting |
| **Multi-Floor Stacking**| Evaluated independently | 3D Heterogeneous Graph Message Passing |
