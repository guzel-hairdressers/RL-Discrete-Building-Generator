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

### Run Performance Benchmarks (Official Protocol)
**MANDATORY BENCHMARK STANDARD**:
* **NEVER benchmark on 25-module toy configurations.**
* All authoritative benchmarks **MUST** evaluate high-density **`120 maxModules` per floor across 4–8 parallel stories on XL Lobed/Complex sites** ($480$ total modules per episode).
* Must compare Pre-Change vs Post-Change on the exact same 10 deterministic seed episodes (`seeds = [100 + i * 23 for i in range(10)]`), validating positive fill ratio, layout scores, and non-empty module placement:
```bash
PYTHONPATH=src python3 benchmarks/benchmark_head_to_head_comparison.py
```


---

## 4. Mandatory Documentation Updates on Push to `main`

Whenever code changes, bug fixes, benchmark runs, or architectural updates are pushed to `main` or release branches (`version/v0.8.1`), **all relevant files in [`agent_notes/`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/README.md) MUST be synchronized and updated**:

1. **Implemented & Discarded Features**: Update [`agent_notes/historical_approaches.md`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/historical_approaches.md).
2. **Bug Fixes & Tracebacks**: Append resolutions to [`agent_notes/issues.md`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/issues.md).
3. **Roadmap & Milestones**: Update status tags in [`agent_notes/roadmap.md`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/roadmap.md).
4. **Performance Data & Benchmarks**: Save categorized run data under [`agent_notes/benchmarks/`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/benchmarks/).
5. **Architectural Guides**: Update guide files in [`agent_notes/guides/`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/guides/).
6. **Central Directory Index**: Keep [`agent_notes/README.md`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/README.md) links up to date.

---

## 5. Strict Branch Verification & Version Governance Protocol

To prevent branch confusion and cross-version contamination, all agents **MUST STRICTLY FOLLOW THIS VERIFICATION PROTOCOL**:

### 1. Pre-Execution Branch & Version Check
Before running code, benchmarks, or making edits:
1. Run `git branch --show-current` to verify the active branch.
2. Cross-reference the active branch with the official version definitions:
   - **`main` (`v0.8.0`)**: Authoritative Multi-Floor 4–8 Story Core Shaft Stacking Optimizer.
     - **Mandatory Files**: [`tests/test_core_stacking.py`](file:///Users/ruslan_faz/Desktop/Work/Thesis/tests/test_core_stacking.py), `FloorEnvironment._stack_commit_checkpoint` in `src/server.py`.
     - **UI Branding**: `Module Lab v0.8.0` in `public/index.html` and `src/server.py`.
     - **Test Suite**: Must run and pass all **162 tests** (`python3 -m unittest discover -s tests -p "test_*.py"`).
   - **`version/v0.8.1` (`v0.8.1`)**: Dynamic Parametric Shape ($k=3,4$) Generator variant.
     - **UI Branding**: `Module Lab v0.8.1` in `public/index.html` and `src/server.py`.
     - **Debug Console**: Hidden developer console via `Ctrl+Shift+D` / `Cmd+Shift+D`.

### 2. Pre-Commit / Pre-Push Diff Inspection
Before staging, committing, or proposing a push:
1. Compare local changes against the remote tracking branch:
   ```bash
   git diff origin/<current-branch> --stat
   ```
2. Verify that core version-defining files are **NOT deleted or replaced** (e.g. `test_core_stacking.py` must never be deleted on `main`).
3. Run the branch-specific test suite to ensure 100% test passing.

### 3. Explicit User Approval Rule
- **NEVER execute `git push` autonomously**. Always present a concise summary of changes and ask for explicit user consent before pushing to remote branches.
