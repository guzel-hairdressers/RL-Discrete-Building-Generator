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
