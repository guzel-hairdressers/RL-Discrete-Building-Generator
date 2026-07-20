# Module Lab v0.6-A — BPE Baseline Stabilization

Module Lab v0.6-A preserves the v0.5.1 parallel PyTorch floor-plan optimizer and stabilizes its BPE geometry path. A FastAPI WebSocket backend performs batched PyTorch policy inference; a dependency-free Canvas interface displays live layouts and aggregate metrics.

## Path 1 stabilization

- Merged type IDs now come from a deterministic canonical geometry signature. Translation, common 2D rotation, node order, and cyclic vertex starts do not change identity; reflection and different along-edge attachments do.
- Full-edge adjacency uses the canonical inclusive 90% overlap threshold with separate 1 cm linear and 0.057° angular tolerances. Edges and ports measure overlap in both segment frames and use the conservative shorter projection, so insertion order cannot change a near-threshold decision.
- Pair frequency counts a deterministic maximum set of node-disjoint occurrences on each floor with a polynomial-time Edmonds blossom matcher, preventing shared-node edges from inflating BPE frequency without exponential visualization stalls.
- Polygon union splits all mutual collinear intervals, snaps only corresponding shared-wall endpoints, and cancels internal subsegments. A merge commits only when every exposed segment forms one fully consumed simple loop. The overlap-length × separation strip allowance is one-sided: closing a small positive gap may add area within that measured budget, but any negative filled-area delta beyond tight numeric epsilon fails locally or rolls back globally.
- Merge plans are transactional. Geometry failures, true holes that the single-ring schema cannot encode, and under-frequency plans preserve both parents and publish no token.
- Reuse scoring is global across floors: every final merged-module occurrence whose token appears at least twice earns exactly +3 points, without topology, component-depth, or floor-count scaling.
- Final episode payloads retain both `placements` and `mergedPlacements`, so the merged/unmerged visualizer toggle remains coherent. Their `dictionary` is the completed episode's palette; the separately returned `nextDictionary` is installed only when the client begins the next episode.
- Merged fill remains component-colored, and rentable-area totals are summed from component categories so cores are not reclassified as rooms by the composite wrapper.
- Geometry controls enforce 1–9 m edges and 3–8 vertices. The fixed catalog is filtered by every polygon's actual edge lengths; a settings transaction commits only when its mode retains the required room, and multi-floor mode also retains a core.

## Run locally

From this directory:

```bash
python3 -m pip install -r requirements.txt
python3 server.py
```

Then open <http://127.0.0.1:8000>. The server prints the selected PyTorch device (`cuda`, `mps`, or `cpu`). Static files are resolved relative to `server.py`, so the command also works when invoked from another working directory.

## Preserved baseline capabilities

- One shared placement, vector-geometry, category, and atrium policy learns from all parallel environments, with placement candidates evaluated in a single batched PyTorch forward pass.
- `parallelEnvironments` controls the floor count. Each floor's normalized outer-boundary and atrium coordinate/radial signatures are encoded separately, then mean/max-pooled so the shared dictionary responds to every floor rather than only aggregate scalar summaries.
- Dictionary slots select from a fixed, constraint-filtered catalog of standardized triangles and quads; geometry is not synthesized by learned coordinate latents. Multi-floor mode uses Core and Room categories with mandatory first Core and Room slots. Canonical single-floor mode exposes a Room-only dictionary with no Core or Corridor classifications. Selected shapes remain fixed for an episode and can only be translated or rotated during placement.
- Agent-controlled atria are learned categorical actions over valid boundary/candidate vector features. An atrium is a site/generation-level action: it is sampled when a new site is created, receives one terminal policy update from that site's first episode, and remains fixed across later episodes until New Site, a structural settings generation, or Reset Policy creates another site. Central mode deterministically chooses the candidate closest to the boundary centroid.
- Exact, symmetric edge contact is required. Vertex touches, gaps, and shared segments shorter than 0.5 m do not create graph edges.
- Multi-floor episodes begin with a realistic 20–30 m² core and enforce core spacing and room-to-core reachability. Single-floor episodes begin with a room and omit all core-dependent topology requirements, penalties, and displayed score rows.
- Fill and rentable percentages are aggregated online by area across every floor. Exact vector daylight, exposed perimeter, and envelope metrics are evaluated at episode completion.
- The browser sends at most one step request at a time and tags messages by generation and episode, preventing stale work after settings or site changes.
- Active training renders cached, viewport-culled polygon paths and graph edges. Exact splayed wall fragments are computed in a cancellable Web Worker only while paused or at episode completion.
- Candidate overlap checks use a spatial broad phase and a bounded, residual-aware attachment frontier. A local CPU stress run with four floors and 50 placement rounds completed in about 10 seconds rather than the roughly 54-second pre-index baseline.

## Controls

All numeric training parameters have synchronized sliders and keyboard-editable fields. Structural edits are validated and debounced before a new generation is requested. Animation speed is local to the browser and never resets training.

The `0°` angle increment is supported and keeps each module's canonical connection orientation. When the three-edge cap makes every module triangular, a 180° attachment flip remains available so strict edge-to-edge growth is still possible. Very fine nonzero increments are sampled across episodes rather than materializing hundreds of rotations at once.

## Tests

Run the focused regression suite from this directory:

```bash
python3 -m unittest discover -s tests -v
```

The suite covers BPE rotational identity and chirality, symmetric slanted/partial overlap thresholds, bounded 5 mm gap closure, fail-closed 5 mm overlap refusal, over-tolerance refusal, polynomial odd-cycle/dense/grid matching, transactional one-sided area adjustment, hard and semantic dictionary limits, room-only single-floor behavior, the exact 8-point average-per-floor triangle penalty, simple exposed boundaries, vector wall preservation, atrium validity, policy-gradient action lifecycles, weighted room transitions, aggregate metrics, WebSocket dictionary lifecycles, UI cancellation/accessibility contracts, and the dynamic multi-environment trainer. BPE tests inherit from `unittest.TestCase`; the documented command therefore collects them without an undeclared pytest dependency.

## Notes

This is a planning and reinforcement-learning prototype, not a life-safety or code-compliance tool. Multi-floor core/corridor stacking remains outside Path 1; the parallel floors and shared dictionary are groundwork for that later constraint layer.
