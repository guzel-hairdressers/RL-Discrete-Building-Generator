# Module Lab v0.9.0

`v0.9.0` is the real-urban-context release of Module Lab — the RL-Discrete-Building-Generator. It embeds each training site in its real-world OpenStreetMap neighborhood, moves multi-floor vertical-circulation **core placement inside the neural policy**, and retrains with a lightweight **A2C** actor–critic update instead of PPO.

The recommended range is 4–8 stories with exact vertical shaft alignment across every floor. `parallelEnvironments` (default `batchSize = 9`) is configurable from 1 to 16 and changes atomically between generations; the count is fixed within an episode.

## What's new in v0.9.0

- **Real Urban OSM Context Integration** — 1,547 real-world OpenStreetMap parcels harvested across 8 cities (New York, London, Tokyo, Singapore, Barcelona, Chicago, Paris, Hong Kong) with neighbor building heights and road meshes from the Context Generator.
- **Split-Screen 3D Urban Context Viewer** — a 50/50 stage split with Three.js WebGL rendering of the real neighborhood (soft shadows, axonometric/perspective cameras, glassmorphic site cards) and live rising 3D module extrusions.
- **Policy-Based Core Placements** — the core stack is no longer a hardcoded pre-step. The Actor–Critic policy evaluates candidate core positions \((x, y)\), angles \(\theta\), and composite features directly, backpropagating building-level GAE returns into the network.
- **RL Refactor: A2C over PPO** — importance-weighted REINFORCE + GAE with a learned value baseline. The default `learningRate` is **0.001** (0.003 is a known A2C mid-run collapse). Optional `lrSchedule` (constant/cosine/linear) + PPO-style `ratioClip` are enableable settings, value-neutral at defaults.
- **Headless / Visuals-Off Toggle** — a `3D Off` control stops the WebSocket payload from carrying display geometry and freezes the renderer, while the RL trajectory stays **bit-identical** (payload −58%, JSON serialization −59%).
- **React 18 + Zustand frontend** — the live UI lives in `frontend/` (Vite-built to `frontend/dist/`); the legacy `public/` canvas app is no longer served.

## Architecture

- **`src/server.py`** — FastAPI + WebSocket backend. Manages multi-floor building transactions, core shaft alignment across 4–8 stories (`FloorEnvironment`), PyTorch Actor–Critic training (`ParallelTrainer`), and WebSocket telemetry streaming.
- **`src/geometry.py`** — vector geometry kernel: Python SAT overlap checks, `_LazyRotationDict` on-demand cell rasterization, and `ctypes` bindings to `src/c/fast_geometry.c`.
- **`src/c/fast_geometry.c`** — native C extension for SAT polygon overlap (`polygons_overlap_c`), point-in-polygon containment, and wall-segment clearance.
- **`src/graph.py`** — BPE polygon merging, adjacency detection, and layout extraction.
- **`frontend/`** — React 18 + Zustand + Vite UI: Three.js 3D viewer (`ThreeViewer`), 2D plan canvas (`PlanCanvas2D`), HUD metrics, and live placement steps.

## Install and run

From this directory:

```bash
python3 -m pip install -r requirements.txt
python3 src/c/build_native.py
python3 src/server.py
```

Open <http://localhost:8000>. Set `PORT` to choose another port.

The native build is optional. `build_native.py` emits `libfast_geometry.dylib` on macOS or `libfast_geometry.so` on Linux, verifies ABI 3, and atomically installs it. It respects `CC` when set:

```bash
python3 src/c/build_native.py --debug
python3 src/c/build_native.py --clean
MODULE_LAB_DISABLE_NATIVE_GEOMETRY=1 python3 src/server.py
```

If the library is absent, incompatible, disabled, or unsupported, the Python geometry reference remains active. Runtime diagnostics report availability, enabled state, ABI, path, and load errors.

### Frontend build

The live UI is a React + Vite app served from `frontend/dist/`. A prebuilt `dist/` is committed; to rebuild after editing `frontend/src/`:

```bash
cd frontend
npm install
npm run build
```

## CPU, MPS, and CUDA

`MODULE_LAB_DEVICE` accepts `auto`, `cpu`, `mps`, `cuda`, or `cuda:N`. `auto` chooses CUDA when available and otherwise CPU. Apple MPS is an explicit override because the policy batches are small:

```bash
MODULE_LAB_DEVICE=mps python3 src/server.py
```

Geometry and proposal generation stay on CPU/native code even when Torch uses an accelerator. A single trainer uses one device. `MODULE_LAB_TORCH_THREADS` controls CPU intra-op threads and defaults to `1`.

## Visuals-off / headless training

The **`3D Off`** toggle (server flag `visuals_enabled`, WebSocket `setVisuals`/`getState` commands, React `ViewToggle` button, and the `&visuals=off` URL param) disables display-geometry transfer and rendering while keeping the RL algorithm, seeded RNG, and trajectory **bit-identical**. It is the foundation for faster, memory-lighter batch runs. See [`agent_notes/guides/visuals_off_guide.md`](agent_notes/guides/visuals_off_guide.md).

## Diagnostics and protocol

Press `Ctrl+Shift+D` / `Cmd+Shift+D` to open the hidden diagnostics panel: last-120 scores, reward components, candidate counts, native-kernel state, process/accelerator memory, and actor/value/entropy/gradient telemetry.

`site`, `placements`, and `episodeDone` events expose a `coreStacking` audit object, including `exactLocalAlignment`, `stackCount`, `violations`, and per-stack `decisionScope: "building"` / `logProbTerms: 1`. Checkpoint upload requires PyTorch 2.6+ (fails closed on older runtimes affected by CVE-2025-32434), is capped at 64 MiB, and is atomically committed after full state validation.

## Tests

```bash
python3 src/c/build_native.py
python3 -m unittest discover -s tests -p "test_*.py"
```

The suite is **170 tests, 100% passing (skipped=2)** — including exact multi-floor core stacking, the loosened `_max_cores_for_site` scaling, empty-episode gradient safety, SE(2)-equivariant policy invariance, and the A2C reframe.

## Benchmarking (mandatory dual protocol)

**1. Speed & throughput** — high-density `L`/`XL` sites (120 max modules/floor across 4–8 parallel stories, 480 total modules per episode):

```bash
PYTHONPATH=src python3 benchmarks/benchmark_head_to_head_comparison.py
```

**2. Quality & RL convergence** — the standard user settings (Site Area Tier `ANY`, Boundary `FREE`, Auto-Changing Sites):

```bash
PYTHONPATH=src python3 benchmarks/benchmark_750_episodes_convergence_any.py
```

## Documentation

- **Architecture & governance** — [`AGENTS.md`](AGENTS.md) (version map, branch protocol, memory conventions)
- **Index of all notes** — [`agent_notes/README.md`](agent_notes/README.md)
- **Guides** — `agent_notes/guides/` (core stacking, BPE merge, visuals-off, benchmarking)
- **Benchmark data** — `agent_notes/benchmarks/` (incl. `v0.9.0-alpha_rl_refactor_2026-08-25.md` for the A2C-vs-PPO and LR-schedule/ratio-clip results)
- **Roadmap, issues, history** — `agent_notes/roadmap.md`, `agent_notes/issues.md`, `agent_notes/historical_approaches.md`
