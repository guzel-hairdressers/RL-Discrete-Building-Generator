# Context Generator

**Context Generator** is a Python and WebGL engine for 3D urban context extraction, parametric parcel generation, and interactive site visualization. It queries real-world urban context scenes from OpenStreetMap (OSM) via parallel spatial Overpass mirrors across global typologies, computes 2D/3D polygon setback envelopes, and renders high-performance interactive 3D WebGL scenes.

---

## Key Features

1. **OSM Urban Context Fetcher (`fetch_custom_site.py`, `fetch_all_osm.py`)**:
   - Queries OpenStreetMap via parallel Overpass server mirrors for 3D building footprints, heights, levels, and road polylines.
   - Extracts context patches centered on target coordinates or user-selected map locations.
   - Computes smart site boundary geometries with sharp mitre yard setbacks, dual-side road curb offsets, and neighbor building footprint subtraction.

2. **Global City Typology Presets**:
   - **Strict Grid / Orthogonal**:
     - `nyc_midtown`: Manhattan NYC (Superhigh density towers on strict rectangular grid).
     - `barcelona_eixample`: Barcelona (Mid/High density octagonal street blocks).
     - `chicago_loop`: Chicago (High density rectangular grid).
   - **Organic / Relaxed / Natural Layouts**:
     - `tokyo_shinjuku`: Tokyo (High density organic road networks & irregular blocks).
     - `london_city`: London (High density medieval/organic layout in City of London).
     - `hongkong_central`: Hong Kong (Extreme superhigh density constrained organic layout).

3. **Procedural Synthetic Context Generator (`procedural_generator.py`)**:
   - Synthesizes 3D contexts on demand using density profiles (`mid_density`, `high_density`, `superhigh_density`).
   - Configurable grid typologies (`strict_grid`, `organic`, `superhigh_tower`).

4. **3D Metrics & Interactive WebGL Viewer (`geometry_3d.py`, `visualizer.py`)**:
   - Computes Site Area (m²), Floor Area Ratio (FAR), Ground Coverage Ratio (GCR), and Avg/Max Height metrics.
   - Generates interactive 3D WebGL preview pages in browser with flat architectural polygon shading, soft directional shadows, and interactive axonometric/perspective cameras.

5. **Multi-Format 3D Simulation Exporters (`exporter.py`, `blender_bridge.py`)**:
   - Exports standard 3D Wavefront `.obj` files for Radiance, Ladybug, PySolar, Rhinoceros/Grasshopper, EnergyPlus, and CFD solvers.
   - Saves structured `.json` dataset files.
   - Includes `blender_bridge.py` for 1-click loading into Blender with sun lights & materials.

---

## Quick Start Guide

### 1. Install Dependencies
```bash
pip install -r requirements.txt
cd app && npm install
```

### 2. Run Interactive Web Application
```bash
cd app
npm run dev
```
Open `http://localhost:5173` in your browser.

### 3. Fetch Custom Site via CLI
```bash
python fetch_custom_site.py --lat 48.8566 --lon 2.3522 --name "Paris Site" --road-setback 2.0 --building-setback 3.0
```

### 4. Fetch Global City Portfolio
```bash
python fetch_all_osm.py
```
