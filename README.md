# Context Generator

**Context Generator** is a Python-based urban 3D context generator designed for solar, shading, daylighting, and building environmental simulations. It extracts real 160m urban context scenes from OpenStreetMap (OSM) via OSMnx across diverse urban typologies (Strict Grid vs. Organic/Relaxed) or procedurally synthesizes realistic 3D building contexts and central testing site boundaries.

---

## Key Features

1. **OSM Urban Context Harvester (`extract_real_3d_osmnx.py`)**:
   - Queries OpenStreetMap (via OSMnx) for 3D building footprints, heights, and levels.
   - Extracts a **160m radius** context patch centered on target coordinates.
   - Identifies the central building, carves it out as the **Testing Site Boundary**, and retains surrounding buildings with 3D height metadata.

2. **Selected City Presets**:
   - **Strict Grid / Orthogonal**:
     - `nyc_midtown`: Manhattan NYC (Superhigh density towers on strict rectangular grid).
     - `barcelona_eixample`: Barcelona (Mid/High density octagonal street blocks).
     - `chicago_loop`: Chicago (High density rectangular grid).
   - **Organic / Relaxed / Natural Layouts**:
     - `tokyo_shinjuku`: Tokyo (High density organic road networks & irregular blocks).
     - `london_city`: London (High density medieval/organic layout in City of London).
     - `hongkong_central`: Hong Kong (Extreme superhigh density constrained organic layout).

3. **Procedural Synthetic Context Generator (`procedural_generator.py`)**:
   - Synthesizes synthetic 3D contexts on demand using density profiles (`mid_density`, `high_density`, `superhigh_density`).
   - Configurable grid typologies (`strict_grid`, `organic`, `superhigh_tower`).

4. **3D Metrics & Interactive WebGL Viewer (`geometry_3d.py`, `visualizer.py`)**:
   - Computes **Site Area ($m^2$)**, **District Floor Area Ratio (FAR)**, **Ground Coverage Ratio (GCR)**, **Avg/Max Height**, and **Sky View Factor (SVF)** proxy.
   - Generates interactive 3D WebGL preview `.html` files in browser with color gradients by height, true 1:1:1 physical aspect scaling, flat architectural polygon shading, and highlighted Gold site parcel.

5. **Multi-Format 3D Simulation Exporters (`exporter.py`, `blender_bridge.py`)**:
   - Exports standard 3D Wavefront `.obj` files for Radiance, Ladybug, PySolar, Rhinoceros/Grasshopper, EnergyPlus, and CFD wind solvers.
   - Saves structured `.json` dataset files.
   - Includes `blender_bridge.py` for 1-click loading into Blender with sun lights & materials.

---

## Quick Start Guide

### 1. Extract Real Urban Contexts from OSM
```bash
python main.py extract --city nyc_midtown
python main.py extract --city tokyo_shinjuku
```

### 2. Generate Synthetic Urban Contexts
```bash
python main.py generate --density high_density --typology strict_grid
python main.py generate --density superhigh_density --typology organic --seed 42
```

### 3. List City Presets
```bash
python main.py list-cities
```

### 4. Load into Blender (Optional Hybrid Workflow)
```bash
blender --background --python blender_bridge.py -- dataset/nyc_midtown_context.json
```
