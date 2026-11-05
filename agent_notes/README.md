# Agent Notes Directory — Module Lab

Welcome to the `agent_notes/` repository directory. This directory serves as the centralized knowledge base, project tracking system, and research proposal archive for human developers and AI coding agents working on the **RL-Discrete-Building-Generator** (Module Lab).

---

## Directory Structure & Contents

```
agent_notes/
├── README.md                          # Central index (this file)
├── proposals.md                       # Master Proposals Register & Rating Matrix
├── historical_approaches.md          # Implemented achievements & discarded/failed approaches ledger
├── issues.md                          # Active issue tracker & bug resolution logs
├── roadmap.md                         # Master step-by-step development roadmap & milestones
├── reports/                           # Deep technical reports & evaluation logs
│   ├── OPTIMIZATION_REPORT.md         # Comprehensive C kernel & profiler benchmark report
│   └── GRAPH_EVALUATION.md            # BPE graph representation report
├── media/                             # Non-text artifacts (screenshots, images)
├── benchmarks/                        # Dated & categorized benchmark datasets
│   ├── README.md                      # Central benchmark directory index & usage guide
│   ├── BENCHMARK_SUMMARY.md           # Speedup metrics & cross-version comparison matrix
│   ├── v0.9.0-alpha_rl_refactor_2026-08-25.md  # RL refactor comparison (A2C vs PPO)
│   ├── 26-08-10_v0.6c-legacy-baseline/
│   ├── 26-08-10_v0.8.0-matched-speedup-eval/
│   ├── 26-08-10_v0.8.0-stress-test-130modules/
│   ├── 26-08-11_v0.8.0-visual-grid-evaluations/
│   └── 26-08-14_v0.8.0-roadmap-execution/
└── guides/                            # Component guides & architectural documentation
    ├── bpe_merge_guide.md             # BPE vocabulary & polygon merge guide
    ├── core_stacking_guide.md         # Multi-floor shaft alignment guide
    ├── visuals_off_guide.md           # Headless / visuals-off toggle architecture
    └── benchmarking_guide.md          # Across-phase benchmarking & metric presentation guide
```

---

## Quick Navigation Links

* **Trainable v0.10.0 graph demo**: [run and inspect training](guides/trainable_graph_demo.md)

* **v0.10.0 shared graph implementation and research gates**: [shared graph guide](guides/shared_graph_v010.md)

* 📜 **Historical Ledger & Failed Approaches**: [`historical_approaches.md`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/historical_approaches.md)
* 🗺️ **Master Roadmap**: [`roadmap.md`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/roadmap.md)
* 📊 **Across-Phase Benchmarking Guide**: [`guides/benchmarking_guide.md`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/guides/benchmarking_guide.md)
* 🎛️ **Headless / Visuals-Off Toggle Guide**: [`guides/visuals_off_guide.md`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/guides/visuals_off_guide.md)
* ⚡ **RL Refactor Benchmark (A2C vs PPO)**: [`benchmarks/v0.9.0-alpha_rl_refactor_2026-08-25.md`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/benchmarks/v0.9.0-alpha_rl_refactor_2026-08-25.md)
* 💡 **RL Architectural Proposals & Ratings**: [`proposals/rl_architecture_proposals.md`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/proposals/rl_architecture_proposals.md)
* 🐛 **Issue Tracker**: [`issues.md`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/issues.md)
* ⚡ **Benchmark Summary**: [`benchmarks/BENCHMARK_SUMMARY.md`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/benchmarks/BENCHMARK_SUMMARY.md)
* 📖 **Management Guidelines**: [`/AGENT_NOTES_GUIDE.md`](file:///Users/ruslan_faz/Desktop/Work/Thesis/AGENT_NOTES_GUIDE.md)

- [Graph-policy architecture evaluation](guides/graph_architecture_evaluation.md) — experimental variants, paired sites, no promoted winner.
- [Graph-only training/runtime validation](reports/v010_graph_only_validation.md) — mode split, raw runtime evidence and remaining proxy gaps.

## 2026-11-04 — bounded shared dictionary latency and correctness

See [the report](../reports/v010_bounded_dictionary_speed.md) for scope and actual room counts. Final `2026-11-04-v010-reuse-headless-{4,8}floors` runs use L/XL, 120 max/floor, seed 123 and frozen source snapshots; each includes one real policy update and a separately timed independent preview. `reuse-final-4floors` was measured with a browser renderer active and is retained separately. No learning/convergence claim follows from one update.

`sampler-matched` compares only the proposal component on identical 480-node graphs at pinned commit `3e9ed018`, not whole episodes. `latency-audit-before/after` are instrumented profiles on different reached graph sizes, not matched throughput ratios. `bounded-dictionary-4floors` contains a failed XL overlap audit; the normalization regression fixes it. `bounded-dictionary-first` has an explicitly incomplete source snapshot. Development and corrected snapshots remain preserved. `bounded-site-audit` aborted on JSON serialization of site metadata; `bounded-site-audit-02` retains six ANY/FREE correctness smoke cases. These are not held-out convergence studies.

- [Angle vocabulary and corrected comparison](reports/v010_angle_proposal_evaluation.md) — three seeds, 60 episodes per strategy, held-out geometry checks; no faster-learning claim.
- [Next algorithm hypotheses](guides/algorithm_hypotheses_2026-11-05.md) — soft orthogonality, boundary conditioning, circulation and efficiency tests.
- [UI overhaul handoff](guides/UI_OVERHAUL_HANDOFF.md) and [shared API contract](contracts/graph_ui_v010.md) — separate worktrees and source ownership.

## 2026-11-05 — individual hypotheses and floor-plate gaps

- [Measured report](reports/v010_hypotheses_benchmarks.md): all eight hypotheses, L/XL4/8-floor timing, urban supplement and limitations; no promoted generator.
- [Gap diagnosis](guides/unplanned_gaps_2026-11-05.md): original geometry checks do not guarantee a continuous floor plate.
- [Graph area assumptions](guides/graph_area_and_realizer_assumptions.md) and [protocol](guides/hypothesis_benchmark_protocol_2026-11-05.md).

## 2026-11-05 — continuity prevention implemented

[Shared-module hole fix](reports/continuity_2026-11-05/README.md): connected boundary-arc growth, protected shared junctions, numeric contact correction and measured endpoint proposals. Final held-out69/69 valid starts, dense12/12 and stochastic-training36/36 pass independent checks with zero raw enclosed-gap area. Three starting-core failures remain explicit. Backend/UI integrated and verified on port8000, including fresh9-floor UI and independent WebSocket runs. Existing data/checkpoints preserved.

## 2026-11-05 — legacy objectives and new spatial constraints audit

[Constraint audit](reports/constraint_audit_2026-11-05/README.md) checks August v0.9.0 source, reproduces two clearance-metric weaknesses, and proposes graph/dictionary open-space relations with explicit uncertainty. Includes multiple-core policy gap: automatic growth currently seeds one core and creates rooms only. Audit/probes only; no training objective or live generator change.

## 2026-11-05 — livable exposure constraints and pause-aware time

[Implemented contract](guides/livable_spatial_constraints_v010.md) and [validation report](reports/livable_spatial_2026-11-05/README.md): livable-only potential-window exposure, multiple-core policy choices, explicit feasibility requirements and an active-time clock.337 backend tests (2 skipped),20 frontend tests; live training/preview verified. Finite pilots have no fully spatial-feasible layouts and establish no convergence improvement; failed/superseded runs are retained.
