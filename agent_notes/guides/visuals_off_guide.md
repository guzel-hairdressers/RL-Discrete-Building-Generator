# Headless / Visuals-Off Toggle — Architecture Guide

**Version**: `v0.9.0` (branch `version/v0.9.0-alpha`)
**Status**: Implemented & browser-verified (2026-08-26)

The **`3D Off`** toggle lets training run headless — the WebSocket payload stops
carrying display geometry, and the browser's Three.js engine stops rendering —
while the RL algorithm, seeded RNG, and trajectory content remain **bit-identical**.
This is the foundation for faster, memory-lighter batch training runs.

---

## 1. How it works (end-to-end)

```
[ViewToggle button]
   │  setVisualsEnabled(!visualsEnabled)   (frontend/src/store/useStore.js)
   ▼
[WebSocket]  cmd:"setVisuals", enabled:bool      (src/server.py websocket_endpoint)
   │
   ▼
ParallelTrainer.visuals_enabled (src/server.py)
   │  when False → build_full_payload gate + step() emit placements/merged = []
   ▼
[WebSocket]  {type:"sync"}  (getState cmd → current_state_event(), ALWAYS full geometry)
   │
   ▼
[React store] "sync" case → repopulate placements/boundaries/metrics
   │
   ▼
[ThreeViewer.jsx] posts {type:"set_visuals_enabled"} to iframes + builds iframe
   URL with &visuals=off when disabled
   │
   ▼
[urban_viewer.js engine] reads initial state from URL param; set_visuals_enabled
   handler flips live flag; animate() skips renderer.render while off (freeze)
```

### Key invariant
The gate strips **display-only** data (`placements`, `mergedPlacements` → `[]`).
The RL algorithm, seeded RNG, and episode content are untouched — so generation is
**bit-identical** whether visuals are on or off. The `getState`/`sync` path always
rebuilds full geometry, which is the load-bearing re-enable mechanism.

---

## 2. Server side (`src/server.py`)

- `ParallelTrainer.visuals_enabled` — plain attribute, **default `True`** (not a
  settings key, so existing sessions are unaffected).
- **Payload gate**: `build_full_payload = visuals_enabled or mode == 'inference'
  or recordTrajectories` — inference mode and trajectory recording always keep
  full geometry.
- **`step()`**: when visuals off, `placements`/`mergedPlacements` emitted as `[]`
  while `metrics.score` etc. keep streaming (monitoring continues).
- **WS commands**:
  - `setVisuals` `{cmd, enabled}` → acknowledges, sets the flag.
  - `getState` → responds `{type: "sync"}` with a full snapshot via
    `current_state_event()` (ignores the gate).

---

## 3. Client side (React + Vite)

Live UI is the React app in `frontend/` → built to `frontend/dist` (served).
`public/` (repo root) is legacy dead code — **not** served.

- `frontend/src/store/useStore.js` — `visualsEnabled` (default `true`),
  `setVisualsEnabled(enabled)` (sends `setVisuals`; on enable also sends
  `getState`), new `sync` case in `handleServerEvent`.
- `frontend/src/components/ViewToggle.jsx` — "3D On/Off" eye button.
- `frontend/src/components/PlanCanvas2D.jsx` — blanks + skips drawing when off.
- `frontend/src/components/ThreeViewer.jsx` — posts `set_visuals_enabled` to
  iframes; `getTargetSrc` builds the iframe URL with `new URL()` and appends
  `&visuals=off` when disabled.
- `frontend/public/scripts/urban_viewer.js` (copied verbatim to
  `frontend/dist/scripts/urban_viewer.js` by the build) — the shared Three.js
  engine loaded by site HTML frames:
  - **Initial state from URL**: `new URLSearchParams(location.search).get('visuals') !== 'off'`.
  - **`set_visuals_enabled` handler** flips the live flag; while off, all scene
    messages are dropped and `animate()` keeps `requestAnimationFrame` running but
    skips `renderer.render` + `drawGizmo` (so re-enable needs no restart).
  - **Born-headless iframes paint white** at init (`setClearColor(0xffffff,1)` +
    `clear`) instead of flashing the site context.

### Why the URL param exists (freeze-leak fix)
Fresh iframes (site changes) default to `visualsEnabled=true` and would render the
site context before the host's `set_visuals_enabled` message landed — so the 3D
visibly "updated" on every episode change while Off. Passing `&visuals=off` at
iframe construction makes new iframes start frozen from their first frame.

### Why no `renderer.clear` on disable
Clearing left a black canvas. Disabling now just **freezes the last frame**;
re-enabling repaints via `getState`/`sync` without a reload.

---

## 4. Benchmark

`benchmarks/benchmark_visuals_off.py` — 120-episode fixed-seed dual subprocess run:

| Metric | Visuals ON | Visuals OFF | Delta |
| :--- | ---: | ---: | ---: |
| Generation content | baseline | **bit-identical** (120 ep × 6 fields) | 0 |
| Mean event payload | 16.99 KB | 7.12 KB | **−58.1%** |
| JSON serialization | 0.459 s | 0.187 s | **−59.2%** |
| Server algorithm step | — | ~1.03× | display formatting is ms/ep |

The dominant, user-visible win is **client-side** (the browser stops shadow-mapped
`renderer.render` + `ExtrudeGeometry` rebuilds per step), which an in-process
benchmark cannot see.

---

## 5. Run / verify

```bash
cd frontend && npm run build        # regenerate frontend/dist (engine + bundle)
python3 src/c/build_native.py
python3 src/server.py               # http://localhost:8000
```

Manual check: open `http://localhost:8000`, toggle `3D On` → `3D Off` → `3D On`.
Off should freeze the last frame (not go black); a site change while Off shows a
blank/white viewer (no flash); re-enabling repaints fully with no reload.
Headless verification harness lives at `/tmp/pwtest/visuals_verify*.js`
(Chrome For Testing + playwright-core, screenshot pixel-stat analysis).
