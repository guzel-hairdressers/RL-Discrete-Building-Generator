# Module Lab v0.8.0

`v0.8.0` is the exact multi-floor core-stacking variant of Module Lab. It carries the building-level intent of the genuine v0.6-c experiment onto the optimized vector-geometry and actor–critic kernel: a core is selected once for the building and committed at the same local transform on every floor, or no floor changes.

The recommended range is 4–8 floors. `parallelEnvironments` remains configurable from 1 to 16 for compatibility, and can be changed through an atomic settings update between generations. The count is fixed within an episode; it is not randomized automatically.

A matched 10-episode CPU comparison against the genuine archived v0.6-c implementation measured 5.3411565833899655 seconds per episode for v0.6-c and 0.8167754751979374 seconds for v0.8.0: a **6.539320468817443x** speed-up. Mean action-step time improved by **14.069987717848928x**, while score, fill, and rentable ratio also increased in that run. Exact provenance, semantic caveats, timing, quality, and memory data are in [OPTIMIZATION_REPORT.md](OPTIMIZATION_REPORT.md).

## Visual results

The [seed-123 PNG contact sheet](visual_results/v0.8.0_seed123_first3_grid.png) renders the actual individual pre-BPE polygons from the first three deterministic episodes as three rows by four floors. Red modules are the exact locked core stack; the matching [JSON manifest](visual_results/v0.8.0_seed123_first3_grid.json) preserves its boundaries, placements, metrics, stack IDs, and alignment audit.

## Core-stacking contract

The exact building signature is:

```text
(module id, rotation angle, local anchor x, local anchor y)
```

Canvas offsets are excluded. The module, rotation, anchor, and local polygon must match on every floor.

- Before a multi-floor site is published, the first learned core is prevalidated against every floor with normal containment, collision, core-spacing, shared-wall, and raster predicates.
- If there is no common transform, the entire group of floor sites is rejected and resampled. Every floor keeps the requested irregular boundary family; no site is enlarged or replaced with a permissive rectangle.
- The first core is a mandatory building action. It creates one placement per floor but exactly one policy decision and one log-probability term.
- Later floor-local candidate lists cannot contain cores. An optional second building core becomes eligible only after every floor has one core and at least six rooms; the policy may then choose a shared stack or a no-stack gate.
- A selected stack is revalidated immediately before mutation. If any floor placement fails, targeted placement-owned checkpoints restore every floor and no stack record or policy term is retained.
- The proven primary core persists across episodes on the same site. A new site or relevant settings generation prepares a new whole-building transaction.

See [core_stacking_guide.md](core_stacking_guide.md) for invariants and WebSocket protocol fields.

## Optimization parity

v0.8.0 shares the v0.8.1 optimization kernel while adding building transactions:

- optional ABI-3 C acceleration for polygon overlap, concave-site containment, shared overlap, tolerant segment overlap, and wall distance, with deterministic Python fallback;
- cached rotation/site bounds, spatial buckets, early AABB rejection, and deferred candidate rasterization;
- bounded per-category proposal quotas and a rotating, stratified 12-edge exposed-frontier view;
- concurrent candidate generation across active floors and one batched policy-scoring call;
- terminal or explicit paused-evaluation BPE, rather than a full graph rebuild after every placement;
- Monte Carlo actor–critic with summed per-trajectory log-probabilities, a learned value baseline, entropy regularization, and gradient clipping; and
- hardware wall time as telemetry only, never as a reward input.

The raw graph proposal was evaluated but not integrated. The existing residual-edge/angle index was faster, and v0.8.0 implements the evaluation's rotating-stratified sampling follow-up. See [GRAPH_EVALUATION.md](GRAPH_EVALUATION.md).

## Install and run

From this directory:

```bash
python3 -m pip install -r requirements.txt
python3 build_native.py
python3 server.py
```

Open <http://127.0.0.1:8000>. Set `PORT` to choose another port.

The native build is optional. `build_native.py` emits `libfast_geometry.dylib` on macOS or `libfast_geometry.so` on Linux, verifies ABI 3, and atomically installs it. It respects `CC` when set.

```bash
python3 build_native.py --debug
python3 build_native.py --clean
MODULE_LAB_DISABLE_NATIVE_GEOMETRY=1 python3 server.py
```

If the library is absent, incompatible, disabled, or unsupported, the Python geometry reference remains active. Runtime diagnostics report availability, enabled state, ABI, path, and load errors.

## CPU, MPS, and CUDA

`MODULE_LAB_DEVICE` accepts `auto`, `cpu`, `mps`, `cuda`, or `cuda:N`. `auto` chooses CUDA when available and otherwise CPU. Apple MPS is an explicit override because the policy batches are small:

```bash
MODULE_LAB_DEVICE=mps python3 server.py
```

Geometry and proposal generation stay on CPU/native code even when Torch uses an accelerator, so GPU speed must be measured rather than assumed. A single trainer uses one device. Two GPUs can run independent policies on separate ports:

```bash
MODULE_LAB_DEVICE=cuda:0 PORT=8000 python3 server.py
MODULE_LAB_DEVICE=cuda:1 PORT=8001 python3 server.py
```

These are independent experiments, not distributed training. Both working from this directory share `outputs/checkpoint.pt`; copy or rename a checkpoint before the other process saves, or use separate working copies. `MODULE_LAB_TORCH_THREADS` controls CPU intra-op threads and defaults to `1`.

## Diagnostics and protocol

Press `Ctrl+Shift+D` or `Cmd+Shift+D` to open the hidden diagnostics panel. It shows the last 120 scores, reward components, candidate counts, native-kernel state, process/accelerator memory, actor/value/entropy/gradient telemetry, and major phase timings. Values update only while the panel is open.

`site`, `placements`, paused evaluation, and `episodeDone` events expose a `coreStacking` audit object. Episode completion also supplies `nextCoreStacking`. Important fields include:

- `enabled`, `status`, `mode`, `floorCount`, and `boundaryPolicy`;
- `siteResampleAttempts` and `initialCandidateCount`;
- `stackCount`, `lockedCoreCount`, `exactLocalAlignment`, and `violations`; and
- stack module, rotation, local anchor, floor/placement IDs, `decisionScope: "building"`, and `logProbTerms: 1`.

Locked placements expose `coreStackId`, `coreStackLocked`, `coreStackTriggerFloor`, and `localAnchor`. `singleFloor: true` reports `disabled-single-floor` and retains floor-local room generation without core stacks.

Checkpoint upload requires PyTorch 2.6 or newer and fails closed on older runtimes because their weights-only loader is affected by [CVE-2025-32434](https://github.com/pytorch/pytorch/security/advisories/GHSA-53q9-r3pm-6pq6). Browser WebSockets are restricted to localhost origins, decoded checkpoints are capped at 64 MiB, and model, strict Adam moment/group, scalar, reward-reference, RNG, and core-generation state is validated before an atomic commit. Saving uses temporary-file replacement and removes partial files after write or replace failures.

## Tests

```bash
python3 build_native.py
python3 -m unittest \
  tests.test_benchmark tests.test_bpe_merge tests.test_core_stacking \
  tests.test_frontend_contract tests.test_geometry tests.test_graph_evaluation \
  tests.test_learned_policy tests.test_native_geometry tests.test_optimization \
  tests.test_trainer tests.test_v06b_dynamic tests.test_v06d_custom
```

This verified non-WebSocket suite completed 157 tests with 2 intentional legacy skips after rebuilding native ABI 3.

Focused building and optimization coverage:

```bash
python3 -m unittest discover -s tests -p "test_core_stacking.py" -v
python3 -m unittest discover -s tests -p "test_native_geometry.py" -v
python3 -m unittest discover -s tests -p "test_optimization.py" -v
python3 -m unittest discover -s tests -p "test_benchmark.py" -v
```

The core tests cover mandatory first stacks on four and eight floors, exact local equality, one building policy term, delayed second-core eligibility, atomic floor-count changes, induced rollback, whole-site irregular resampling, exhausted-preflight non-commit, and single-floor disabling.

In the restricted development sandbox used for this pass, in-process FastAPI/Starlette `TestClient` WebSocket tests block in `TestClient.__enter__` even for an otherwise empty FastAPI application, while direct trainer tests complete. The two WebSocket tests are therefore not included in the 157-test claim. Use a real server-process integration check there and rerun `tests/test_websocket.py` or full discovery on a normal local or CI host.

## Benchmark

The harness runs every module/seed pair in a fresh interpreter and records full episodes, p50/p95 timing, count-weighted profiler phases, RSS/tracemalloc/accelerator memory, quality, diversity, and stable action/layout/dictionary hashes.

The matched current artifact is [`benchmark_results/v0.8.0_seed808_matched_v06c_10ep.json`](benchmark_results/v0.8.0_seed808_matched_v06c_10ep.json); its genuine archived counterpart is [`benchmark_results/historical_v0.6c_seed808_10ep.json`](benchmark_results/historical_v0.6c_seed808_10ep.json). A harder default-setting run is retained separately in [`benchmark_results/v0.8.0_seed123_10ep.json`](benchmark_results/v0.8.0_seed123_10ep.json). See [OPTIMIZATION_REPORT.md](OPTIMIZATION_REPORT.md) for exact configurations, commit provenance, reproduction, and limitations.
