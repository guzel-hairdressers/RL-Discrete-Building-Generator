# Module Lab v0.3 — Parallel PyTorch Floor Plan Optimizer

Module Lab v0.3 is a local research prototype for training a shared, parameterized modular floor-plan policy across several building floors at once. A FastAPI WebSocket backend performs batched PyTorch policy inference; a dependency-free Canvas interface displays live layouts and aggregate metrics.

## Run locally

From this directory:

```bash
python3 -m pip install -r requirements.txt
python3 server.py
```

Then open <http://127.0.0.1:8000>. The server prints the selected PyTorch device (`cuda`, `mps`, or `cpu`). Static files are resolved relative to `server.py`, so the command also works when invoked from another working directory.

## What changed from v0.2

- One shared placement, vector-geometry, category, and atrium policy learns from all parallel environments, with placement candidates evaluated in a single batched PyTorch forward pass.
- `parallelEnvironments` controls the floor count. Each floor's normalized outer-boundary and atrium coordinate/radial signatures are encoded separately, then mean/max-pooled so the shared dictionary responds to every floor rather than only aggregate scalar summaries.
- Dictionary modules are synthesized directly from learned 8D Normal actions. Core, corridor, and room slots are mandatory; remaining categories are learned with public-mode masking. Shapes are fixed after sampling for an episode and can only be translated or rotated during placement.
- Agent-controlled atria are learned categorical actions over valid boundary/candidate vector features. An atrium is a site/generation-level action: it is sampled when a new site is created, receives one terminal policy update from that site's first episode, and remains fixed across later episodes until New Site, a structural settings generation, or Reset Policy creates another site. Central mode deterministically chooses the candidate closest to the boundary centroid.
- Exact, symmetric edge contact is required. Vertex touches, gaps, and shared segments shorter than 0.5 m do not create graph edges.
- The first module is a realistic 20–30 m² core unless single-floor mode is enabled. Core spacing, corridor width, room-to-core crossing limits, and special-room reachability are checked explicitly.
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

The suite covers strict and partial edge overlap, vector wall preservation, atrium validity, learned latent geometry, policy-gradient action lifecycles, weighted room transitions, aggregate metrics, WebSocket transactions, UI cancellation/accessibility contracts, and the dynamic multi-environment trainer.

## Notes

This is a planning and reinforcement-learning prototype, not a life-safety or code-compliance tool. Multi-floor core/corridor stacking percentages are intentionally not active in v0.3; the parallel floors and shared dictionary are groundwork for that later constraint layer.
