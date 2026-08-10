# Module Lab v0.8.1

`v0.8.1` is the optimized continuation of the v0.7-D discrete-building generator. It keeps the vector-geometry, dynamic-shape, topology, atrium, and BPE behavior while moving avoidable work out of the placement loop. It is the independent-floor variant; the stacked multi-story-core experiment is maintained separately as v0.8.0.

The final-code representative result is a **5.919x** speed-up over the same-configuration root v0.7-D baseline on the harder 10-episode lobed workload (exact ratio: 5.919139752213579x). A separately retained 20-episode rectangular artifact measured a 5.067408708026263x paired speed-up at an earlier point in development; it is historical paired evidence, not a measurement of the final release code. Both were CPU runs on one Linux host. See [OPTIMIZATION_REPORT.md](OPTIMIZATION_REPORT.md) for exact values, configurations, quality comparisons, and limitations.

## Visual results

The [seed-123 PNG contact sheet](visual_results/v0.8.1_seed123_first3_grid.png) renders the actual individual pre-BPE polygons from the first three deterministic episodes as three rows by four independently optimized floors. Its matching [JSON manifest](visual_results/v0.8.1_seed123_first3_grid.json) preserves the exact boundaries, placements, categories, and episode metrics.

## What changed

- Candidate generation is bounded by per-category quotas and a rotating, stratified 12-edge frontier view. An incremental exposed-edge index replaces repeated exhaustive anchor scans.
- Site bounds, rotation bounds, spatial buckets, and placement AABBs reject impossible proposals before exact geometry. Raster cells are materialized only for candidates that survive vector checks.
- Active floors generate candidates concurrently; all surviving candidates are scored in one batched policy call. Tiny CPU policy tensors default to one Torch thread to avoid thread-pool overhead.
- Full layout-graph extraction and BPE merging run at episode completion or on explicit paused evaluation, not after every placement step.
- The optional ABI-3 C kernel accelerates polygon overlap, concave-site containment, shared-wall overlap, tolerant segment overlap, and point-to-segment distance. Its semantics are differential-tested against the Python reference.
- Learning is now Monte Carlo actor–critic. Placement log-probabilities are summed within each floor trajectory and averaged across floors, the critic predicts normalized terminal return, and the update includes normalized entropy, Huber value loss, and gradient clipping.
- Hardware wall time is telemetry only. Reward uses deterministic frontier growth and geometry/quality terms, so changing CPU, GPU, or system load does not directly change the learning target.
- A diagnostics panel, hidden by default, shows score history, reward components, candidate counts, native-kernel state, memory, actor/critic statistics, and phase timings. Toggle it with `Ctrl+Shift+D` or `Cmd+Shift+D`.

The detailed graph proposal was benchmarked and was not integrated. The existing exact residual-edge index was faster and produced the same legal actions after authoritative geometry filtering. See [GRAPH_EVALUATION.md](GRAPH_EVALUATION.md).

## Install and run

From this directory:

```bash
python3 -m pip install -r requirements.txt
python3 build_native.py
python3 server.py
```

Open <http://127.0.0.1:8000>. Set `PORT` to use another port.

The native build is optional. `build_native.py` selects a C11 compiler, builds `libfast_geometry.dylib` on macOS or `libfast_geometry.so` on Linux, verifies ABI 3, and atomically installs the result. Set `CC` to select a compiler. Useful commands are:

```bash
python3 build_native.py --debug
python3 build_native.py --clean
MODULE_LAB_DISABLE_NATIVE_GEOMETRY=1 python3 server.py
```

If the library is absent, incompatible, or unsupported on the platform, geometry automatically uses the deterministic Python implementation. The diagnostics panel reports whether native geometry is available and enabled, as well as any load error.

On macOS, install the Xcode command-line tools if no compiler is available. The default device remains CPU because the policy batches are small; request MPS explicitly when testing a larger workload:

```bash
MODULE_LAB_DEVICE=mps python3 server.py
```

## Device selection and two GPUs

`MODULE_LAB_DEVICE` accepts `auto`, `cpu`, `mps`, `cuda`, or `cuda:N`. `auto` chooses CUDA when available and otherwise CPU. Geometry and proposal search remain CPU/native work; only the Torch policy and learner use the selected accelerator, so a GPU is not guaranteed to improve small interactive runs.

One trainer uses one device. To use two GPUs today, run independent training processes on different devices and ports:

```bash
MODULE_LAB_DEVICE=cuda:0 PORT=8000 python3 server.py
MODULE_LAB_DEVICE=cuda:1 PORT=8001 python3 server.py
```

Open one browser session per port. These are independent policies, not distributed data-parallel replicas. Both processes use `outputs/checkpoint.pt` when the UI save command is used, so copy or rename a checkpoint before saving from the other process, or run separate working copies.

Checkpoint upload requires PyTorch 2.6 or newer and fails closed on older runtimes because their weights-only loader is affected by [CVE-2025-32434](https://github.com/pytorch/pytorch/security/advisories/GHSA-53q9-r3pm-6pq6). Browser WebSockets are restricted to localhost origins, decoded checkpoints are capped at 64 MiB, and model, scalar, reward-reference, RNG, and canonical Adam group/moment state is validated before an atomic commit. Saving uses temporary-file replacement and removes partial files after write or replace failures.

For CPU experiments, `MODULE_LAB_TORCH_THREADS` controls Torch intra-op threads and defaults to `1`.

## Tests

Build the native library first if native differential coverage is wanted, then run:

```bash
python3 build_native.py
python3 -m unittest discover -s tests -p "test_*.py"
```

Focused optimization checks:

```bash
python3 -m unittest discover -s tests -p "test_native_geometry.py" -v
python3 -m unittest discover -s tests -p "test_optimization.py" -v
python3 -m unittest discover -s tests -p "test_benchmark.py" -v
python3 -m unittest discover -s tests -p "test_graph_evaluation.py" -v
```

To exercise the Python fallback through the ordinary geometry suite:

```bash
MODULE_LAB_DISABLE_NATIVE_GEOMETRY=1 \
  python3 -m unittest discover -s tests -p "test_geometry.py" -v
```

In the restricted development sandbox used for this optimization pass, in-process FastAPI/Starlette `TestClient` WebSocket tests can block while waiting for a cross-thread event-loop wakeup. The behavior reproduced across dependency versions, while direct trainer tests completed normally. Use a real server-process integration check there, and run `tests/test_websocket.py` on a normal local or CI host.

## Benchmark

The harness launches every module/seed pair in a fresh interpreter, fixes Python and Torch seeds, records 10 or 20 complete episodes, and emits wall-time, p50/p95 step time, count-weighted phase profiling, RSS/tracemalloc/accelerator memory, quality metrics, diversity signatures, and deterministic action/layout/dictionary hashes.

```bash
python3 scratch/benchmark.py --help
```

The final-code evidence is checked in as [`scratch/results_10ep_lobed_seed123_v081_release.json`](scratch/results_10ep_lobed_seed123_v081_release.json) and [`scratch/results_10ep_lobed_seed123_v081_release.csv`](scratch/results_10ep_lobed_seed123_v081_release.csv). Exact reproduction commands and all historical artifacts are listed in [OPTIMIZATION_REPORT.md](OPTIMIZATION_REPORT.md). The rectangular paired result and superseded candidate artifacts remain point-in-time historical evidence. None should be treated as a measurement of an unbenchmarked device.

## Learning and reward notes

This release deliberately uses a Monte Carlo critic rather than claiming PPO, TD, or off-policy training. The expensive terminal checks remain the source of truth. The critic reduces the variance of the terminal REINFORCE-style update without introducing a proxy intermediate reward, while trajectory aggregation avoids overweighting short or prematurely dead-ended floors.

BPE contributes exactly `+3` for each globally reused merged-module occurrence. Unmerged triangles, topology failures, dictionary-cap breaches, constructibility, fill, rentable area, daylight, envelope efficiency, and a deterministic relative-frontier term remain visible in terminal metrics. Generation time and size-normalized time are still measured, graphed, and benchmarked, but do not affect reward.
