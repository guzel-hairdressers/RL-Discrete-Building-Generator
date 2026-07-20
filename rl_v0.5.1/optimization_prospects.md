# Future Optimization Prospects (rl_v0.6+)

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


