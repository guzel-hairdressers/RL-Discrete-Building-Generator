# Reinforcement Learning Optimization Specifications: Parallelized Modular Floor Plan Optimizer

This document defines the system specifications, constraints, metrics, and architecture for the next iteration of the Modular Floor Plan Optimization Agent. The agent is to design a high-performance Python/PyTorch backend connected to a clean, responsive HTML visual canvas.

---

## 1. High-Performance Parallelized Architecture (Python + PyTorch)
To achieve maximum speed and training efficiency:
- **Python Backend (`server.py`)**: Implement all geometry calculations, collision detection, and reinforcement learning code in Python.
- **PyTorch GPU Training**: 
  - Build the policy model using PyTorch.
  - The model must detect and utilize GPU hardware: `device = torch.device("cuda" if torch.cuda.is_available() else "cpu")`.
  - Ensure compatibility with multi-GPU rigs (e.g., dual RTX 5080 systems) for training parallelization.
- **Parallel Environments**: Simulate multiple boundary filling processes in parallel using multiprocessing or batch rollout vectorization in PyTorch.
- **WebSocket Streaming**: Stream placement steps, dictionary shapes, metrics, and weights in real-time to the HTML client for visual rendering.

---

## 2. Procedural Bespoke Module Generator (No Trivial Templates)
**Avoid Trivial Solutions:** The dictionary must not be populated with static, hardcoded shapes (like "elbow link", "soft octagon", L-shapes) that have minor size tweaks. 
- **Bespoke Generation**: Programmatically generate arbitrary closed polygons by choosing random numbers of edges, sizes, and internal angles that respect the parameters:
  - **Min Edge**: Controllable slider from $0.0\text{m}$ to $30.0\text{m}$ (with $0.5\text{m}$ increments and text input).
  - **Max Edge**: Controllable slider from $0.0\text{m}$ to $30.0\text{m}$ (with $0.5\text{m}$ increments and text input).
  - **Max Edges (Sides)**: Capped at $12$ edges.
  - **Dictionary Cap**: Capped at $20$ unique modules.
  - **Angle Increment**: Controllable slider from $0.0^\circ$ to $90.0^\circ$ (with $0.5^\circ$ increments and text input).
- **Module Classification**:
  - **Cores**: Vertical circulation blocks.
  - **Corridors**: Physical circulation spaces.
  - **Rooms**: Habitable spaces.
  - **Special / Public Rooms**: Large rooms ($\ge 25\text{ m}^2$) that behave differently in transition checks.

---

## 3. Strict Edge-to-Edge Connectivity (No Islands, No Point Touches)
The previous layout results had disconnected modules and point-to-point corner contacts. These are structurally illegal.
- **No Islands**: The entire layout must be a single connected graph. Every module placed (except the first) must connect to at least one already placed module.
- **No Corner-Only Connections**: Modules touching only at a vertex ($0\%$ shared edge length) are strictly **illegal**.
- **Minimum Overlap Check**: A connection is valid only if modules share an edge segment of at least $1.0\text{m}$ (or $\ge 25\%$ of the shorter segment length).
- **Reward Full-Edge Connections**: The reward function must strongly favor full-edge matches and penalize tiny partial sliding contacts that leave odd notches.

---

## 4. Circulation & Topological Constraints
- **Corridor Width**: Corridors, elbow links, and transitional spaces must be physically narrow (maximum width of $1.5\text{m}$).
- **No Floating Corridors**: Corridors not connected to habitable spaces or cores are illegal. Any chain of corridors must terminate at a Room or Core.
- **2-Room Transition Limit (Space Syntax)**:
  - In standard residential settings, reaching a core from any standard room must pass through **at most 2 intermediate standard rooms**.
  - **Special Room Exception**: Passing through a "Special Room" or "Public Room" does not increment the 2-room transit cap.
  - A valid path to a core must exist through a corridor, a special room, or direct connection, adhering to the 2-room transition limit.
- **Daylight Exclusions**:
  - Do **not** measure daylight for corridors and cores.
  - Daylight (proximity within $6\text{m}$ to the outer boundary or atrium) is only required/evaluated for Rooms and Special Rooms.
- **Exterior Corridor Penalty**: Corridors placed along the site's outer boundary block daylight from habitable areas and must be heavily penalized.

---

## 5. Rentable Area Metrics
- **Rentable Area**: Sum of the areas of Rooms and Special Rooms.
- **Non-Rentable Area**: Sum of the areas of Corridors and Cores.
- **Rentable Ratio**: Proportional rentable area to the total placed area. Maximizing this ratio is preferred, but the model must maintain a healthy balance to ensure cores are large enough to serve the building population (cores can be disregarded if the single-floor checkbox is ticked).

---

## 6. Atrium & Boundary Geometry
- **Arbitrary Atriums**: The model must generate and handle arbitrary polygonal atriums (avoiding simple hardcoded rectangles) as boundary holes.
- **Transparency**: Render atriums/holes with **no fill** (transparent) so the background millimeter grid remains visible.

---

## 7. Policy Weight Explanation
To help verify model updates:
- **Dynamic Optimization**: The policy weights $w_f$ represent preferences for the 12 features. The agent learns these by running full episodic rollouts, calculating the final advantage (the score compared to a moving average baseline), and performing gradient ascent:
  $$w_f \leftarrow w_f + \alpha \cdot \text{Advantage} \cdot \sum_{t=0}^{T} \gamma^{T-t} \left(\Phi_f(t) - E[\Phi_f(t)]\right)$$
- If layouts with a high rentable ratio score well, the advantage is positive, and the weights for those features will increase, driving future action selection.

---

## 8. Frontend UI and Scale Bar
- **Keyboard Inputs**: Every slider must have an input box next to it supporting numeric typing.
- **Scale Bar**: Revert to the geographic staggered layout showing ticks at $0, D, 2D, 5D, 10D$ (where $D$ is dynamically calculated based on zoom).
- **Clean Styles**: Solid colors for module categories (cores, corridors, rooms, special rooms). Remove all diagonal hatches and dashed corridor guide lines.
