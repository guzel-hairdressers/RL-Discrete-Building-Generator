# Module Lab v0.7-D — High-Performance C-Accelerated Parallel Floor Plan Optimizer

`v0.7-D` is the high-performance, C-accelerated release of the Module Lab Reinforcement Learning Discrete Building Generator. It builds upon `v0.6-D` (Parametric Triangles & Quads + Dynamic Palette Synthesis) and introduces low-level C acceleration, lazy rotation cell rasterization, AABB pre-filtered BPE port merging, CPU policy execution tuning, and per-step profiler metering.

---

## Key Performance Innovations in v0.7-D

1. **C-Accelerated Vector Geometry (`fast_geometry.c`)**:
   - Implements native C extensions for Separating Axis Theorem (SAT) polygon overlap (`polygons_overlap_c`) and point-in-polygon containment (`polygon_inside_site_c`).
   - Bound via Python `ctypes` in `geometry.py` with automatic fallback to pure Python if uncompiled.

2. **Lazy Rotation Cell Rasterization (`_LazyRotationDict`)**:
   - Defers expensive grid rasterization (`rasterize_polygon`) until rotation cells are explicitly queried by the Pass 2 placement fallback.
   - Eliminates rasterization overhead across 720+ pre-calculated rotation variants during dictionary synthesis.

3. **AABB Pre-Filtered BPE Port Merging (`graph.py`)**:
   - Wraps placement port overlap comparisons with `bounds_of` bounding-box intersection pre-checks.
   - Filters out 90%+ of distant port pairs before computing symmetric segment overlaps.

4. **Optimized CPU PyTorch Policy Dispatch**:
   - Selects `cpu` execution for small scalar RL action policy tensors on Apple Silicon macOS, avoiding PyTorch MPS driver synchronization overhead.

5. **Accurate Per-Step Profiling & Cumulative Timing**:
   - `Step Total`: Average wall-clock execution duration for a single floor placement step.
   - `Episode Total`: True cumulative wall-clock duration ($\sum \text{Steps} + \text{Terminal Phase}$).

---

## Preserved Baseline Capabilities

- **Parametric Triangle & Quad Synthesis**: Shape policy outputs logits for edge count $k \in \{3, 4\}$, edge lengths, and internal angles.
- **Dictionary Limit Breach Penalty**: Subtracts squared penalties when the shape dictionary size exceeds limits.
- **Agent-Initiated Preliminary Stop Action**: Action space includes a `STOP` candidate, enabling early layout termination.
- **Multi-Floor Atrium & Core Topologies**: Supports core/room topological validation, single vs multi-floor atriums, and constituent component coloring.

---

## Run Locally

```bash
# Build C extension (optional, automatic fallback exists)
clang -O3 -shared -fPIC -o libfast_geometry.so fast_geometry.c

# Run Python server
python3 server.py
```

Then open `http://localhost:8000` in your web browser.

---

## Running Tests

```bash
python3 -m unittest discover -s tests -p "test_*.py"
```
