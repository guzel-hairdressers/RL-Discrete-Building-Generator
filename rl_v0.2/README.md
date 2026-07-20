# Module Lab v0.2 — Parallel PyTorch Floor Plan Optimizer

This folder contains the parallelized PyTorch RL floor plan optimizer, supporting hardware acceleration (GPU/MPS/CUDA) and live WebSocket visualization.

## Quick Start Instructions

1. **Install Python Dependencies** (using pip):
   ```bash
   pip install -r requirements.txt
   ```
   *(Note: Ensure you have PyTorch installed with CUDA support if running on an NVIDIA GPU machine, or standard installation for macOS MPS/CPU)*

2. **Start the PyTorch Backend Server**:
   ```bash
   python3 server.py
   ```
   The backend will print which hardware device it is executing on (e.g. `cuda` or `cpu`/`mps`) and launch a WebSocket server at `ws://127.0.0.1:8000/ws`.

3. **Launch the Visual Interface**:
   Simply open `index.html` in any browser, or run a simple local web server:
   ```bash
   python3 -m http.server 3000
   ```
   and navigate to `http://localhost:3000`.

---

## Technical Enhancements in v0.2

- **Hardware Acceleration**: Policy weights are optimized using PyTorch Policy Gradients (REINFORCE) with full CPU/GPU compatibility.
- **Model-Learned Shapes**: Avoids static pre-programmed shape templates. The generator dynamically constructs bespoke grid-closed polygons using the agent's parameters.
- **Topological Space Syntax Verification**:
  - Implements a connectivity graph to prevent isolated islands and vertex-only point touches (all connections require $\ge 0.5\text{m}$ edge overlap).
  - Rooms must reach a core with $\le 2$ intermediate standard room crossings (Special rooms and corridors are transit-exempt).
  - Corridors must be narrow ($\le 1.5\text{m}$) and terminate at habitable rooms.
- **Rentable-to-Filled Space Metrics**: Rentable area calculation represents rooms and special rooms, encouraging a balanced leasable footprint.
- **Dynamic Building Envelope Daylighting**: Daylight is calculated using point-to-loop distance checks against the *actual, dynamically traced exterior walls and interior courtyard boundaries of the growing building shape*, rather than static site boundaries.
