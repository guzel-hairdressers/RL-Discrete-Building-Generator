# Module Lab v0.6-C — Multi-Floor Core Stacking

> [!CAUTION]
> **TEMPORARILY UNSUPPORTED / DO NOT EDIT**
> `rl_v0.6-c` is currently marked as **temporarily unsupported**. Please do not edit or modify files in this directory.

Module Lab v0.6-C extends the complete v0.5.1 floor-plan optimizer with physical multi-floor core stacking. A FastAPI WebSocket backend performs batched PyTorch policy inference; a dependency-free Canvas interface displays live layouts, BPE modules, and aggregate metrics.

## Run locally

From this directory:

```bash
python3 -m pip install -r requirements.txt
python3 server.py
```

Then open <http://127.0.0.1:8000>. The server prints the selected PyTorch device (`cuda`, `mps`, or `cpu`). Static files are resolved relative to `server.py`, so the command also works when invoked from another working directory.

## v0.6-C stacking behavior

- `parallelEnvironments` represents floors in one building whenever single-floor mode is off.
- A Core action is never committed independently per floor. One module ID, local `(x, y)` anchor, and rotation is validated against every outer boundary, atrium, and existing placement, then committed atomically on all floors.
- Each physical core stack is sampled once from a building-level categorical over pooled all-floor features, has one shared stack ID, and contributes its one exact placement-policy log-probability term regardless of floor count. A pooled no-stack action gates independent room decisions on steps where both choices exist.
- The first stack is placed before rooms. Subsequent rooms grow from the locked core attachment frontiers; later cores use the same all-floor legality and atomic-commit path.
- The mandatory Core/Room dictionary seed is filtered to the same legal 1:1, 1:2, or 2:1 edge ratios used by placement, preventing an isolated first core with no possible room frontier.
- Fixed dictionary actions are filtered by every actual edge (`1–9m`) and the active `3–8` vertex cap. A settings transaction that cannot supply the required compatible multi-floor Core/Room seed is rejected before the current generation changes.
- Site generation reserves a common structural rectangle before atrium selection. Atrium actions that intersect it are removed from the policy action set.
- If concave floor boundaries have no common reserve, their notches are closed to the existing axis-aligned envelopes. The site extents do not grow, and the adaptation is reported in protocol metadata.
- If even the envelope fallback cannot fit the reserve, the new settings/site transaction fails before commit, leaving the prior generation intact.
- Single-floor mode uses independent room-only dictionaries, removes Core/Corridor classifications and core-dependent topology checks, and disables stacking adaptation and metrics.
- Terminal events keep the completed episode's dictionary paired with its placements and publish the prepared vocabulary separately as `nextDictionary`; the client installs it only when the next episode begins.
- Every final merged-module occurrence whose token is reused globally earns exactly +3 points, independent of topology validity, component depth, and floor count.

All v0.5.1 geometry, topology, learned-policy, BPE merging, pause/evaluation, visualization, checkpoint, and WebSocket behavior remains present. See [core_stacking_guide.md](core_stacking_guide.md) for invariants and protocol fields.

Terminal and read-only evaluation scores apply the canonical unmerged-triangle penalty: `8.0 × (post-BPE triangle count / floor count)`.

## Controls

All numeric training parameters have synchronized sliders and keyboard-editable fields. Structural edits are validated and debounced before a new generation is requested. Animation speed is local to the browser and never resets training.

The `0°` angle increment is supported and keeps each module's canonical connection orientation. When the three-edge cap makes every module triangular, a 180° attachment flip remains available so strict edge-to-edge growth is still possible. Very fine nonzero increments are sampled across episodes rather than materializing hundreds of rotations at once.

## Tests

Run the focused regression suite from this directory:

```bash
python3 -m unittest discover -s tests -v
```

The suite covers the complete v0.5.1 regressions plus exact three-floor alignment, pooled single-policy-term accounting, no-stack gating, stale-candidate and episode-transition atomicity, canonical single-floor behavior, boundary fallback, atrium filtering, and deterministic New Site transactions.

## Notes

This is a planning and reinforcement-learning prototype, not a life-safety or code-compliance tool. Core alignment is exact in local 2D coordinates; corridor and room stacking are intentionally outside v0.6-C scope.
