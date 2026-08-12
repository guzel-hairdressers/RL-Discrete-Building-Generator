# Benchmark Summary & Performance Ledger

This document tracks execution speedups, step throughput, and memory performance across version releases of the **RL-Discrete-Building-Generator** (Module Lab).

---

## Performance Comparison Matrix

| Version Branch | Architecture | Mean Step Time | Mean Episode Time | Speedup vs Baseline | Primary Acceleration Factor |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `version/v0.6-c` | Legacy Python SAT | $11.4\,\text{ms}$ | $1.48\,\text{s}$ | $1.0\times$ (Baseline) | Full Python SAT overlap & Python spatial hash |
| `version/v0.7-d` | C Dynamic Shape | $3.2\,\text{ms}$ | $0.41\,\text{s}$ | $3.61\times$ | Initial `ctypes` bindings to `fast_geometry.c` |
| `main` (`v0.8.0`) | Multi-Floor Core Stacking | $0.81\,\text{ms}$ | $0.226\,\text{s}$ | **$6.54\times$** | Native C SAT `polygons_overlap_c` + spatial hash lookup |
| `version/v0.8.1`| Dynamic Shape $k=3,4$ | $0.94\,\text{ms}$ | $0.250\,\text{s}$ | **$5.92\times$** | On-demand dynamic parametric shape rasterization |

---

## Core Benchmark Metrics (v0.8.0)

* **Episode Runtime Target**: $< 250\,\text{ms}$ per 4–8 story episode $\to$ **Achieved ($226\,\text{ms}$)**
* **Step Acceleration**: 14.07x speedup per candidate evaluation step ($11.4\,\text{ms} \to 0.81\,\text{ms}$)
* **Unit Test Suite**: 159 unit tests passed cleanly (`OK`).
