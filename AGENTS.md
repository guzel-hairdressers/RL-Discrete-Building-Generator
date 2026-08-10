# Agent Instructions & Project Architecture — Module Lab v0.8.0

Welcome to the **RL-Discrete-Building-Generator** (Module Lab) codebase.

---

## 1. Versioning & Governance Structure

- **`main` Branch**: Authoritative **`v0.8.0`** release at root — Exact Multi-Floor 4–8 Story Core Shaft Stacking Optimizer.
- **`version/v0.8.1` Branch**: **`v0.8.1`** release — Dynamic Parametric Shape ($k=3,4$) Generator with 5.92x speedup and hidden debug console (`Ctrl+Shift+D`).
- **Legacy Variant Branches**:
  - `version/v0.6-a`: Alternative candidate placement anchor search.
  - `version/v0.6-b`: Dynamic palette & parametric proposals variant.
  - `version/v0.6-c`: Frontier growth scoring and core stacking experiment.
  - `version/v0.6-e`: Relative frontier reward shaping and BPE penalty weighting.
  - `version/v0.7-b`: PyTorch MPS device baseline.
  - `version/v0.7-d`: C-accelerated dynamic shape baseline.
  - `prototype/simplified_no_rl`: Heuristic p5.js prototype generator.

---

## 2. Key Architecture Components (v0.8.0)

- **`server.py`**: FastAPI & WebSocket backend. Manages multi-floor building transactions, core shaft alignment across 4–8 stories (`FloorEnvironment`), PyTorch Actor–Critic policy training (`ParallelTrainer`), and WebSocket telemetry streaming.
- **`geometry.py`**: Vector geometry kernel. Contains Python SAT overlap checks, `_LazyRotationDict` on-demand cell rasterization, and `ctypes` bindings to `fast_geometry.c`.
- **`fast_geometry.c`**: Low-level C extension implementing native SAT polygon overlap (`polygons_overlap_c`), point-in-polygon containment (`polygon_inside_site_c`), and wall segment clearance.
- **`graph.py`**: BPE polygon merging, adjacency detection, and layout extraction.
- **`index.html`, `app.js`, `styles.css`**: Live HTML5 Canvas frontend. Renders multi-floor sites, HUD metrics, and placement steps in real time.

---

## 3. Running & Verifying Code

### Build Native C Extension & Run Web Daemon
```bash
python3 build_native.py
python3 server.py
```
Open `http://localhost:8000` in your web browser to view live training.

### Run Unit Tests
```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

### Run Performance Benchmarks
```bash
python3 scratch/benchmark.py
```
