# Future Optimization Prospects (rl_v0.6+)

> [!CAUTION]
> **TEMPORARILY UNSUPPORTED / DO NOT EDIT**
> `rl_v0.6-c` is currently marked as **temporarily unsupported**. Please do not edit or modify files in this directory.

This document outlines long-term architectural optimizations and design exploration paths following the implementation of the `rl_v0.5` (Pack Simple + BPE Merge) baseline.

---

## 1. Option B: RL-Proposed Shape Parameters (Dynamic Palette Selection)

If the fixed basic dictionary in `v0.5` yields layouts that feel too rigid or blocky, we can restore shape synthesis freedom while keeping the search space clean.

### The Mechanism
Instead of selecting a pre-baked shape ID, the RL policy outputs a continuous/discrete action vector representing:
1. **Width & Height Index**: Proposing indices from the discrete `EDGE_PALETTE` (e.g., action `[2, 4]` maps to `2.0m × 3.0m`).
2. **Angle Index**: Proposing indices representing internal angles in 15° or 30° steps (e.g., action `[4, 8]` maps to `60°` and `120°` for a parallelogram).
3. **Symmetry/Type Flags**: Dictating if the shape is a rectangle, trapezoid, parallelogram, or irregular quad.

### Why this is better than raw vertex latent vectors
- **Guaranteed Legibility**: Shapes are generated using the clean parametric formulas of `_connection_ready_source_polygon`, but with parameters snapped directly to the edge palette and 15° increments.
- **Perfect Grid Fit**: Because the generated shapes only use angles from the 15° grid and lengths from the palette, they are guaranteed to match other shapes perfectly, avoiding the validation failures of raw coordinates.
- **Infinite Variety**: Allows the model to generate thousands of unique valid combinations of width, height, and angle, while keeping the underlying structure standard.

---

## 2. Relaxing or Eliminating Angle Increments

The user asked: *Could we get rid of the strict angle increments since we are combining basic shapes afterwards?*

### Assessment of Free-Angle Stacking

| Aspect | With Strict Increments (15°) | Without Increments (Free-Angle) |
|---|---|---|
| **Edge Alignment** | High probability of exact collinear alignment. | Very low probability of flush alignment unless shapes naturally adapt. |
| **BPE Merge Frequency** | High. Many shapes share the same contact interfaces, leading to frequent merges. | Extremely low. Slanted connections at arbitrary angles (e.g. 13.4° vs 14.1°) will be counted as unique, preventing standardization. |
| **Manufacturability** | Excellent. All joints are standard angles (90°, 60°, 45°). | Poor. Custom angular joints required for every single intersection. |

### The Verdict
Eliminating angle increments completely would make the BPE merge fail because the probability of two shapes sharing the *exact* same relative angle decreases to near-zero. 

**However, we can relax it to 5° or 10° increments.** 
If we relax the step size:
- We increase geometric freedom.
- We must generate more rotation variants (e.g. 72 rotations for 5° increments instead of 24 for 15°).
- This increases candidate generation time, but is still highly parallelizable on CPU/GPU.

---

## 3. Dynamic BPE Feedback (Evolutionary Dictionary)

Currently, BPE merges are evaluation-only; the RL agent always starts packing with the same basic quads and triangles.

### The Feedback Mechanism
1. At the end of episode $E$, BPE identifies the top 3 most frequent merged modules (e.g., an L-shape and a Z-shape).
2. These 3 merged modules are **added** to the active dictionary for episode $E+1$.
3. The RL agent can now choose to place these pre-assembled modules directly.
4. Over many episodes, the dictionary "evolves" to contain large, complex, standardized structural assemblies.

This mimics how real construction systems evolve standard modular kits over time.

---

## 4. Relative Generation Time Reward Shaping (Placement Frontier Growth Potential)

When the policy network constructs layouts, it is highly desirable for it to preserve "growth potential" — placing shapes in a way that doesn't block future modules or create tight dead-ends, but instead leaves open edges/frontiers for future connections. 

Mathematically, a layout with high growth potential has a larger number of valid placement edges/frontier candidates at each step. This larger candidate pool increases the computation time required by the environment's search/collision evaluation loops. Therefore, **generation time per episode** acts as a direct proxy for the size and complexity of the valid placement frontier.

### The Mechanism
We can introduce a reward/penalty term based on the **relative generation time** of the layout:
1. **Relative Scaling**: To prevent hardware variations (device compute capability, parallel worker processes) from skewing the metric, measure the episode's placement time relative to either the first episode of the run or a rolling moving average of placement times.
2. **Setting-Change Baselines**: If settings (like boundary types, parallel environments, max modules per floor) change, the raw baseline generation time changes instantly. To prevent a massive spike in penalty, the reference baseline should not instantly drop to 0, but rather preserve the pre-change penalty level and gradually transition over subsequent epochs.

### Trivial Solution Exploits & Future Directions (Guidance for Future Agents)
Future agents reading this proposal should analyze and address potential trivial exploits:
- **Trivial Smaller-Shape Exploit**: The policy model could try to cheat the relative generation time metric by placing a large number of very small shapes. Doing so naturally increases the quantity of possible connection edges, which artificially inflates search and evaluation time without actually creating meaningful or high-quality architectural layout growth.
- **Evaluation & Assessment**:
  - Is this trivial solution actually bad? Placing smaller shapes might help fill layout gaps, but too many small shapes degrade structural modularity and increase manufacturing complexity.
  - Future agents should evaluate this trade-off (e.g. by tracking average module size and unmerged shape counts alongside relative time).
- **Potential Avoidance Solutions**:
  - **Size-Normalized Time**: Normalize the generation time relative to the average size or area of the placed shapes.
  - **Penalty Scaling**: Scale the relative time reward inversely with the number of placed shapes below a certain size threshold.
  - **Frontier Density Metric**: Instead of using raw generation time as a proxy, directly count unique *high-quality* connection vectors or keep a strict ratio of open frontier edges to placed shapes.

---

## 5. Boundary Representation Enrichment

To help the reinforcement learning policy conceptualize the spatial layout boundaries and avoid crossing them (especially in runs without hardcoded masking filters, such as `rl_v0.6-e`), we can enrich the boundary representation beyond a simple list of coordinate vertices:

1. **Signed Distance Field (SDF)**: Precompute a 2D grid overlay of the site. For each grid cell, store the signed distance to the nearest boundary edge (positive inside, negative outside).
2. **Edge Normal Vectors**: Represent the boundary as a sequence of directed segments with inward-pointing normal vectors, allowing the site encoder to capture boundary directions.
3. **Dynamic Proximity Features**: For each candidate placement, compute the shortest distances from its corners/centroid to the boundary segments and feed these directly into the placement network.

---

## 6. BPE Merging Optimization Goals & Shape Regularization Strategies

While the current BPE merging objective awards a linear `+3.0` point bonus for every constituent module occurrence in globally reused merged shapes (encouraging deep, long multi-shape merges), this unconstrained depth incentive occasionally yields elongated or irregular composite geometries. Future sub-versions should evaluate the following alternative merging objectives and shape regularization strategies:

### 1. Long Merges vs. Merges of Similar Lengths (Constituent Count Regularization)
- **Current Approach**: Rewards maximum constituent depth (e.g., merging 6+ shapes into long continuous chains yields up to +18 points).
- **Alternative (Equal Depth / Length Penalty)**: Introduce a variance penalty or cap on constituent shape counts (e.g., target 2–4 constituent modules per composite).
- **Trade-off**: Prevents overly complex, non-standard composite outlines while preserving high vocabulary compression.

### 2. Area & Aspect-Ratio Regularization
- **Current Approach**: BPE evaluates topological and geometric validity but ignores composite aspect ratio and area balance.
- **Alternative**: Reward merges between constituent shapes of similar areas ($A_1 \approx A_2$) or penalize high composite aspect ratios ($\text{perimeter}^2 / \text{area}$).
- **Trade-off**: Keeps composite modules visually regular, convex, and structurally sound for modular manufacturing.

### 3. Small Triangle Elimination Priority
- **Current Approach**: Merges are selected purely based on maximum global pair frequency $f(A, B)$.
- **Alternative**: Scale merge pair selection score by a weighting factor that prioritizes pairs containing unmerged small triangles (e.g., $S = f(A, B) \times w_{\text{triangle}}$).
- **Trade-off**: Directly eliminates awkward leftover single triangles early in the episode, maximizing floor plan usability.

---

## 7. Automatic Domain Generalization via Auto-Changing Sites (`Auto-Change Sites`)

To prevent the reinforcement learning agent from overfitting to a single static site boundary during extended training sessions, future sub-versions should incorporate an **Auto-Change Sites** curriculum feature:

- **Mechanism**: Automatically trigger `New Site (N)` at the completion of every episode or every $K$ episodes.
- **UI Control**: Exposed as a pre-checked toggle checkbox (`Auto-Change Sites: ON` by default) in the controls panel.
- **RL Benefit**: Forces the policy network to generalize across diverse site geometries, aspect ratios, and atrium hole configurations rather than memorizing a fixed spatial coordinate map.

---

## 8. Site Property Boundary vs. Architectural Facade Walls & Interior Partitions

**CRITICAL DEFINITIONS & BOUNDARY EVALUATION**:
- **Site Property Boundary (`site["outer"]`)**: This represents the property plot / parcel boundary line set before generation. It is **NOT** a building exterior wall! Placed shapes do not need to flush-align with or touch this property boundary line.
- **Exterior Facade Walls**: The outer perimeter boundary of the combined union/cluster of placed shapes. Edges whose normal vectors point outward into open site space or atrium openings are the **actual exterior facade walls** of the building.
- **Interior Partition Walls**: Edges shared between adjacent placed shapes inside the building footprint.
- **No Penalization for Property Line Gap**: Unshared edges of placed shapes facing open site space are legitimate exterior facade walls. They must NEVER be penalized as "internal exposed walls" or subtracted from the layout score.


