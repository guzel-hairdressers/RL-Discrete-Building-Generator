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

- **`src/server.py`**: FastAPI & WebSocket backend. Manages multi-floor building transactions, core shaft alignment across 4–8 stories (`FloorEnvironment`), PyTorch Actor–Critic policy training (`ParallelTrainer`), and WebSocket telemetry streaming.
- **`src/geometry.py`**: Vector geometry kernel. Contains Python SAT overlap checks, `_LazyRotationDict` on-demand cell rasterization, and `ctypes` bindings to `src/c/fast_geometry.c`.
- **`src/c/fast_geometry.c`**: Low-level C extension implementing native SAT polygon overlap (`polygons_overlap_c`), point-in-polygon containment (`polygon_inside_site_c`), and wall segment clearance.
- **`src/graph.py`**: BPE polygon merging, adjacency detection, and layout extraction.
- **`public/index.html`, `public/app.js`, `public/styles.css`**: Live HTML5 Canvas frontend. Renders multi-floor sites, HUD metrics, and placement steps in real time.

---

## 3. Running & Verifying Code

### Build Native C Extension & Run Web Daemon
```bash
python3 src/c/build_native.py
python3 src/server.py
```
Open `http://localhost:8000` in your web browser to view live training.

### Run Unit Tests
```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

### Run Performance Benchmarks
```bash
python3 benchmarks/benchmark.py
```

---

## 4. Mandatory Documentation & Cross-Subversion Synchronization Rules

Whenever code features, bug fixes, performance optimizations, or architectural updates are implemented on `main` or any release branch across present and future versions (`v0.8.x`, `v0.9.x`, `v1.0.x`, etc.):

1. **Mandatory Feature & Code Subversion Sync**:
   Unless a feature or bug fix is strictly variant-specific, **all general code features, geometry fixes, speed optimizations, and spatial constraints MUST be synchronized into the source code across all active subversion branches** of that version family (e.g. `version/v0.8.1`, `version/v0.9.1`, etc.) **BEFORE pushing to remote repositories**.

2. **Mandatory Documentation Sync**:
   **All relevant files in [`agent_notes/`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/README.md) MUST be updated and synchronized before pushing to remote**:
   - **Implemented & Discarded Features**: Update [`agent_notes/historical_approaches.md`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/historical_approaches.md).
   - **Bug Fixes & Tracebacks**: Append resolutions to [`agent_notes/issues.md`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/issues.md).
   - **Roadmap & Milestones**: Update status tags in [`agent_notes/roadmap.md`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/roadmap.md).
   - **Performance Data & Benchmarks**: Save categorized run data under [`agent_notes/benchmarks/`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/benchmarks/).
   - **Architectural Guides**: Update guide files in [`agent_notes/guides/`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/guides/).
   - **Central Directory Index**: Keep [`agent_notes/README.md`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/README.md) links up to date.

---

## 5. Git Push Approval Rule

- **Do NOT execute `git push` unless explicitly instructed**: AI agents must **NEVER** push commits to remote repositories (`git push`) unless the user explicitly commands it in a prompt (e.g. "push", "push once done"). Keep all code edits, commits, subversion feature sync, and documentation updates local until explicit user consent is given.

---

## 6. Standard Roadmap Execution Protocol (`/goal` & Roadmap Requests)

Whenever a user requests to run the development roadmap (e.g. via `/goal` or "run roadmap till step X"):

1. **Iterative Phase Execution**:
   - For each target phase, subphase, and decision node in [`agent_notes/roadmap.md`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/roadmap.md), implement the specified architectural features, algorithm improvements, and geometric constraints.
2. **Debug Until 100% Functional**:
   - Debug and fix all regressions until all unit tests pass (`python3 -m unittest discover -s tests -p "test_*.py"`).
3. **Mandatory Post-Phase / Post-Subphase Comparative Benchmarking**:
   - **Full Phase Benchmarks**: Run **50 episodes** after each major phase (`--episodes 50`).
   - **Subphase Benchmarks**: Run **25 episodes** after each subphase (`--episodes 25`).
   - **Comparative Baseline Evaluation**: Benchmarks MUST be executed **after EACH phase and subphase** comparing directly against the prior baseline state (`--module-dir baseline=<prior_state> --module-dir contender=.`).
   - **Metric & Learning Dynamics Evaluation**: Evaluate whether the changes improved performance: score progression, variance reduction $\sigma$, rentable ratio, 0% topology violation rate, BPE reuse saturation, and unmerged triangle penalties. If changes are regressions, iterate and fix before proceeding.
   - **Cross-Subversion Universality Benchmarks**: Benchmarks MUST ALSO be executed on all active subversion branches (e.g. `version/v0.8.1` dynamic parametric shape generator) to test whether architectural updates are universally useful across variant mechanics or if there are specific domain/extent boundaries to their use cases.
4. **Decision Node Transition**:
   - Evaluate decision branches (e.g. variance thresholds, convergence checks) based on the comparative benchmark data before advancing to subsequent phases.
5. **Mandatory Documentation Sync**:
   - Synchronize all files in [`agent_notes/`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/README.md) (`historical_approaches.md`, `issues.md`, `roadmap.md`, `benchmarks/`, `guides/`), saving reports under [`agent_notes/benchmarks/`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/benchmarks/).
6. **Cross-Subversion Code Sync**:
   - Propagate and test all general features across all active subversion branches of the version family (e.g., `version/v0.8.1`, `version/v0.9.1`, etc.).
7. **Local Commit & User Push Approval**:
   - Commit all changes locally; do not execute `git push` unless explicitly commanded by the user.

