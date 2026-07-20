# Module Lab v0.6-E — Soft Boundary & Atrium Penalty Learning

This branch implements soft RL boundary constraint learning with comprehensive penalty functions across external site boundaries and internal atrium holes, alongside hard vertex constraints and agent-initiated preliminary stop actions.

## v0.6-E features & mechanisms

- **Comprehensive Boundary & Atrium Penalty**: Evaluates and penalizes partial boundary crossings, complete external placements ($3\times$ weight), site boundary enclosures ($5\times$ weight), and internal atrium hole violations ($2\times$ weight) using a dynamically scaling penalty factor.
- **Hard Vertex Constraint**: Candidate placement generation strictly filters out shapes where 100% of vertices lie outside the outer site boundary.
- **Agent-Initiated Preliminary Stop Action**: Supports early layout termination via policy-chosen `STOP` action before reaching maximum placement caps.
- **Dynamic Palette & Materialized Rotations**: Synthesizes clean polygons with 5°/10° placement rotations.
- **Relative Frontier Growth Reward**: Normalizes frontier growth against rolling episode baselines.

---

## Run locally

From this directory:

```bash
python3 -m pip install -r requirements.txt
python3 server.py
```

Then open <http://127.0.0.1:8000>. The server prints the selected PyTorch device (`cuda`, `mps`, or `cpu`). Static files are resolved relative to `server.py`, so the command also works when invoked from another working directory.

## Preserved baseline capabilities

- One shared placement/category/shape/atrium policy learns from every parallel
  environment, with placement candidates evaluated in one batched PyTorch call.
- Each floor retains its vector boundary and atrium descriptor before learned
  mean/max pooling; agent, central, and no-atrium modes remain available.
- Exact vector containment, overlap, adjacency, envelope, daylight, topology,
  BPE merging, and component-colored merged rendering remain authoritative.
- The first dictionary slot is a 20–30m² core and the second is a room. Later
  slots choose core or room, with no more than two core types per dictionary.
  In single-floor mode every slot is an ordinary room and core-dependent
  topology checks are disabled.
- Unmerged top-level triangles receive the canonical −8 point penalty per
  average triangle per floor.
- WebSocket generation/episode guards, cancellable wall computation, viewport
  culling, spatial broad phase, and the residual attachment frontier are kept.

## Controls

All numeric training parameters have synchronized sliders and keyboard-editable fields. Structural edits are validated and debounced before a new generation is requested. Animation speed is local to the browser and never resets training.

The `0°` placement increment keeps the canonical connection orientation (with
the required triangular 180° flip). Fine nonzero increments are materialized:
5° creates 72 variants and 10° creates 36 variants before symmetry deduplication.

## Tests

Run the focused regression suite from this directory:

```bash
python3 -m unittest discover -s tests -v
```

The suite covers discrete palette/lattice validity, rotation counts, size-ratio
enforcement, behavior-policy gradients, rolling reward transitions, BPE,
geometry, topology, WebSocket transactions, and frontend contracts.

## Notes

This is a planning and reinforcement-learning prototype, not a life-safety or
code-compliance tool. Core stacking is developed separately in `rl_v0.6-c`.
