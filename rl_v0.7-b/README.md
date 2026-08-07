# Module Lab v0.6-B — Dynamic Palette + Relative Frontier Reward

This branch implements Path B from the root `rl_optimization_specs.md` while
retaining the complete v0.5.1 application and BPE visualizer.

## v0.6-B additions

- The shape policy now selects a factorized `(width index, height index, angle
  index, type index)` action. Geometry is synthesized from the 1m–9m edge
  palette and a common 5° angular lattice; raw vertex prediction and static
  shape-ID selection are not used.
- Rectangle, parallelogram, symmetric-trapezoid, irregular-quad, and triangle proposals are
  validated before sampling. Invalid edge lengths, angles at or below 40°,
  self-intersections, invalid core areas, and dictionary area ratios above 5:1
  are masked out.
- Placement increments of 5° and 10° are fully materialized (up to 72 rotation
  variants), keeping BPE-compatible connections while increasing freedom.
- Terminal reward includes a bounded relative generation-time/frontier term.
  It uses rolling baselines, transitions those baselines over five episodes
  after structural settings changes, directly measures legal frontier growth,
  normalizes time by module area, and penalizes tiny-shape inflation.
- Episode metrics expose the raw and normalized timings, frontier potential,
  rolling references, exploit penalty, transition state, and final reward term.
- The stabilized BPE path uses rotation-only/reflection-sensitive token
  identities, symmetric tolerant contacts, one-sided transactional snap-area
  bounds, and polynomial exact node-disjoint occurrence matching.
- Episode-completion payloads keep the completed palette beside completed
  geometry and defer the separate `nextDictionary` until the next episode.
- Every final merged-module occurrence whose token is reused globally earns
  exactly +3 points, without topology, component-depth, or floor-count scaling.

Focused v0.6-B coverage lives in `tests/test_v06b_dynamic.py`.

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
