# Model-Driven & Policy-Controlled Core Placement Strategies

`agent_notes/proposals/core_placement_proposals.md`

This proposal details the two-phase architectural design for transitioning core placement from fixed centroid heuristics to fully model-driven and policy-controlled core generation.

---

## Executive Summary & Rating Matrix

| Proposal ID | Proposal Name | Phase | Rating | Primary Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **PROP-12** | Dynamically Determined Core Placement | Phase 1 (Immediate) | **HIGH (Immediate Focus)** | Dynamically computes 1 vs 2 core requirement by site area/floors, but core candidate placement, rotation, shape variant, and attached sequential Core 2 placement are 100% policy-decided. |
| **PROP-13** | Fully Policy-Controlled Core Generation | Phase 2 (Roadmap) | **HIGH (Advanced Goal)** | Gives policy total decision autonomy over core count, placement timing ($t=k$), core shape variant selection, and attached vs detached placement via egress distance field signals. |

---

## Detailed Proposals

### PROP-12: Dynamically Determined Core Placement (Phase 1 — Immediate Implementation)

* **Concept**:
  * **Core Count Rule**: Core count requirement (1 vs 2 cores) is dynamically computed based on site polygon area and story count (e.g. 2 cores for sites $> 600\text{ m}^2$ or stories $\ge 6$).
  * **Model-Decided Candidate Anchors**: The policy selects initial Core 1 placement $(x_1, y_1, \theta_1, \text{CoreShapeID})$ at step $t=0$ from a spatial candidate pool generated via **Signed Distance Fields (SDFs)**, principal boundary axes, and structural setback contours.
  * **Sequential Attached Core 2 Placement**: Core 2 is placed sequentially at step $t=k$, **attached to the active module frontier** (ensuring 100% geometric alignment without bridge gaps) or detached in an unbuilt wing zone.
* **Rating**: **HIGH (Immediate Focus)**
* **Justification**: Eliminates the "bridge misalignment" problem of placing two fixed distant cores early. Frontier-attached Core 2 placement guarantees zero-gap layout generation while giving the model total freedom over position, rotation $\theta$, and core shape geometry.

---

### PROP-13: Fully Policy-Controlled Core Generation (Phase 2 — Roadmap Item)

* **Concept**:
  * **Autonomous Decision Autonomy**: The policy network $\pi_\theta(a_t | s_t)$ decides autonomously **when** to add a core, **how many** cores to place, and **when core placement is complete** (`FINISH_CORES` action).
  * **State Feature Signals**:
    - *Egress Radius Field*: Spatial distance field from any footprint point to the nearest placed core.
    - *Unserviced Frontier Ratio*: Percentage of valid site area beyond fire egress safety limits ($> 30\text{m}$).
    - *Core Area Penalty*: Penalizes unnecessary cores since cores consume space across all floors ($4-8$ stories).
* **Rating**: **HIGH (Advanced Goal)**
* **Justification**: Allows the neural policy to autonomously discover site-specific core requirements—small $300\text{ m}^2$ sites naturally learn single-core layouts, while sprawling multi-wing sites autonomously trigger attached secondary egress cores.

---

## Implementation Sequence

```
Step 1: Implement PROP-12 (Dynamically Determined Cores with SDF Setbacks & Frontier-Attached Core 2)
   │
   ▼
Step 2: Train & Validate Policy Layout Score Gains on 4–8 Story Multi-Floor Buildings
   │
   ▼
Step 3: Implement PROP-13 (Policy-Controlled Core Count & Egress Radius State Signals)
```
