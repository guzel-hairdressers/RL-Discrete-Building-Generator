# Module Lab — RL floor plan optimizer

An interactive, dependency-free browser prototype for optimizing a reusable modular kit inside fixed site boundaries. It turns the design problem into a compact reinforcement-learning environment and makes every placement, metric, and learned preference visible.

## Run

From this directory:

```bash
python3 -m http.server 4173
```

Then open `http://localhost:4173`.

## What is implemented

- A proportion-driven kit of squares, 3:2 bays, compact bays, paired bays, symmetric clipped bays, restrained L-bays, and soft octagons. Shared dimensions improve edge matching; compactness, angle quality, aspect ratio, and edge harmony form a regularity score.
- Fixed site boundaries with optional atriums, including an agent-selected atrium strategy.
- Exact polygon containment and polygon-overlap validation in addition to the fast occupancy grid. Concave boundary crossings, thin overlaps, atrium engulfment, and illegal edge crossings are rejected; legal shared edges remain allowed.
- Random convex hulls, radial non-convex sites, deeply lobed star sites with long asymmetric appendages and multiple re-entrant notches, randomized T-sites, L/U sites, rectangles, and a mixed random curriculum.
- Deep-lobed sites expose lobe count, boundary vertex count, notch depth, and lobe reach. Lobe directions, dominant lengths, anisotropy, and global rotation are sampled independently, so no downward direction or single peak is privileged.
- An episodic REINFORCE-style policy. It samples feasible module/rotation/anchor actions, stores the policy gradient, and updates its weights from the final multi-objective reward.
- Single-floor mode and multi-floor-ready classification into cores, transitions, and rooms.
- Fill, dictionary reuse, daylight proximity, constructibility, compactness, travel, perimeter, size-ratio, connectivity, and envelope metrics.
- Animated training, pause/resume, policy reset, pan/zoom/fit, and a metre-accurate staggered scale bar.
- A random episode orientation basis breaks the world-axis lock. The first core/room chooses that basis, later modules may explore one angle increment to either side, and an orthogonal-only control remains available.
- Optional shearing happens only while the dictionary is created: it produces a fixed parallelogram module that is subsequently rigid, reusable, and limited to rotation/translation like every other type.
- Corridors are topological connectors rather than generic yellow rooms. A corridor action is feasible only after two rooms exist, must contact at least two placed modules, is penalized at the exterior, and is rewarded for connecting rooms and cores. Linear, splayed, and elbow families are supported.
- Atriums are scored by occupied perimeter engagement and adjacent circulation. The policy can reject them entirely when their daylight/circulation benefit does not repay lost area and perimeter.

## RL formulation

The state is the occupied-cell field, exact site/atrium geometry, module-use counts, circulation graph, episode orientation basis, and core/corridor placement state. Actions are feasible `(module, angle-step rotation, anchor)` tuples. The policy scores each candidate from coverage, shared contact, reuse, daylight, compactness, regularity, orientation coherence, corridor topology, atrium utility, controlled novelty, travel, and sequence. A softmax policy explores early and gradually cools. Episode reward includes the same architectural objectives rather than optimizing fill alone.

The 1 m occupancy grid accelerates action generation, while final feasibility is checked against the exact polygons. For production CAD exchange, the predicates should eventually move to an adaptive-precision geometry kernel.

## Geometry regression test

```bash
node tests/boundary-collision.test.js
```

The test includes a concave-notch regression that vertex-only checks miss, atrium and thin-overlap cases, legal shared-edge cases, then dozens of seeded plans across every boundary family. It also verifies non-orthogonal first placements, valid angle increments, sheared kits, interior topological corridors, and zero exact-geometry violations.

## Batch evaluation and PNG export

```bash
node scripts/evaluate-plans.js
python3 scripts/render-arrangements.py
```

The evaluator compares grid-only, edge-heavy, and hybrid proposal policies on matched sites, then runs a larger parameter sweep. Results and the six selected plans are written to `outputs/best-arrangements/`.
