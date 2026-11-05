# Categorized Benchmark Results & Performance Ledgers

`agent_notes/benchmarks/`

This directory contains categorized, reproducible benchmark datasets, execution metrics, and visual evaluations for the **RL-Discrete-Building-Generator** (Module Lab).

---

## Directory Organization

```
agent_notes/benchmarks/
├── README.md                                          # Central Directory Index & Usage Guide (this file)
├── BENCHMARK_SUMMARY.md                                # Performance Comparison Matrix & Speedup Metrics
├── v0.9.0-alpha_rl_refactor_2026-08-25.md             # RL refactor comparison (A2C vs PPO), v0.9.0-alpha
├── 26-08-10_v0.6c-legacy-baseline/                    # Baseline v0.6-c Python SAT benchmark datasets (Seed 808)
│   ├── historical_v0.6c_seed808_10ep.csv
│   └── historical_v0.6c_seed808_10ep.json
├── 26-08-10_v0.8.0-matched-speedup-eval/              # Matched speedup evaluation vs v0.6c (6.54x speedup)
│   ├── v0.8.0_seed808_matched_v06c_10ep.csv
│   └── v0.8.0_seed808_matched_v06c_10ep.json
├── 26-08-10_v0.8.0-stress-test-130modules/            # High-capacity workload evaluation (130 modules, Seed 123)
│   ├── v0.8.0_seed123_10ep.csv
│   └── v0.8.0_seed123_10ep.json
├── 26-08-11_v0.8.0-visual-grid-evaluations/           # Visual layout rendering grids & JSON floor plan layouts
│   ├── v0.8.0_seed123_first3_grid.json
│   └── v0.8.0_seed123_first3_grid.png
└── 26-08-14_v0.8.0-roadmap-execution/                 # Phase 3–7 roadmap-execution benchmark runs
```

---

## Benchmark Artifacts Overview

1. a configuration-matched comparison against the genuine historical
   `rl_v0.6-c` tree at commit `49692e04`; and
2. a larger default-style v0.8.0 workload with agent-selected atriums.

Both use the subprocess-isolated benchmark harness. The JSON contains machine,
Python, PyTorch, per-phase timing, memory, quality, diversity, and deterministic
layout/action hashes; the CSV retains one row per measured episode.

## Matched v0.6-c comparison

Both versions used seed `808`, lobed boundaries, no atrium, four floors,
`maxModules=10`, `dictCap=6`, `angleStep=90`, and no warmup. The historical
artifacts are copied unchanged from the isolated commit run.

| Metric | Historical v0.6-c | v0.8.0 | Change |
|---|---:|---:|---:|
| Mean episode wall time | 5.3412 s | 0.8168 s | **6.54x faster** |
| Mean action-step time | 527.782 ms | 37.511 ms | **14.07x faster** |
| Mean score | 25.815 | 39.344 | +13.529 |
| Mean fill ratio | 0.19109 | 0.36396 | +90.5% |
| Mean rentable ratio | 0.46121 | 0.84799 | +83.9% |
| Topology-valid episodes | 100% | 100% | unchanged |
| Unique layout/action hashes | 10 / 10 | 10 / 10 | unchanged |
| Observed peak RSS | 538,607,616 B | 581,517,312 B | +8.0% |

The algorithms do not emit identical action counts: historical v0.6-c averaged
38 placements while v0.8.0 averaged 29.3 placements and achieved higher
fill. Wall time is therefore reported both per complete episode and per action
step; both favor v0.8.0.

Reproduce the current half from the `v0.8.0` directory:

```bash
python3 benchmarks/benchmark.py \
  --module-dir v0.8.0=. \
  --episodes 10 --warmup 0 --seed 808 \
  --settings '{"boundaryType":"lobed","atriumPolicy":"none","parallelEnvironments":4,"maxModules":10,"dictCap":6,"angleStep":90.0}' \
  --max-steps 2000 --episode-timeout 120 --run-timeout 1260 \
  --json-out benchmark_results/v0.8.0_seed808_matched_v06c_10ep.json \
  --csv-out benchmark_results/v0.8.0_seed808_matched_v06c_10ep.csv
```

Files:

- `historical_v0.6c_seed808_10ep.json` / `.csv`
- `v0.8.0_seed808_matched_v06c_10ep.json` / `.csv`

## Larger v0.8.0 workload

This separate absolute run used seed `123`, four floors, lobed boundaries with
agent-selected atriums, `maxModules=130`, `dictCap=10`, and `angleStep=15`.
It is not used in the historical speed-up ratio.

- Episode wall time: mean `1.4607 s`, p50 `1.3356 s`, p95 `2.0379 s`.
- Action-step time: mean `47.867 ms`, p50 `44.811 ms`, p95 `83.859 ms`.
- Mean score/fill/rentable ratio: `31.719` / `0.25898` / `0.75435`.
- Mean modules: `19.7`; topology-valid episodes: `100%`.
- Diversity: `10/10` unique layout hashes and action hashes.
- Observed peak RSS: `583,000,064 bytes`; traced peak growth: `13,100,347 bytes`.

Reproduce it with:

```bash
python3 benchmarks/benchmark.py \
  --module-dir v0.8.0=. \
  --episodes 10 --warmup 0 --seed 123 \
  --settings '{"boundaryType":"lobed","atriumPolicy":"agent","singleFloor":false,"publicMode":false,"parallelEnvironments":4,"maxModules":130,"learningRate":0.001,"minEdge":3.0,"maxEdge":9.0,"maxEdges":8,"dictCap":10,"angleStep":15.0,"coreSpacing":8.0,"travelLimit":12,"allowCorridors":false,"allowStop":false}' \
  --max-steps 2000 --episode-timeout 120 --run-timeout 1260 \
  --json-out benchmark_results/v0.8.0_seed123_10ep.json \
  --csv-out benchmark_results/v0.8.0_seed123_10ep.csv
```

## 2026-11-04 graph-policy architecture experiments

- [Pilot 01 — completed and inconclusive](2026-11-04-v010-architecture-pilot-01/README.md): 18 episodes, three models; no convergence, throughput or winner claim.
- Pilot 02 runs separately on the corrected concave containment implementation; do not combine scores across the two environment versions.

### Graph-only runtime diagnostics — 2026-11-04

- [Before hot-path profiles](2026-11-04-v010-hotpath-before/): L/XL, 120 max/floor, four floors, instrumented active steps.
- [Intermediate after profiles](2026-11-04-v010-hotpath-after/): changed trajectories; not a matched speedup benchmark. Includes failed intermediate completions.
- Graph-only training [run 01](2026-11-04-v010-graph-only-training-01/), [run 02](2026-11-04-v010-graph-only-training-02/), [run 03](2026-11-04-v010-graph-only-training-03/): separate source snapshots, raw failures, training and preview times; L/XL, 120 max/floor, four floors. One seed, no convergence claim.

## 2026-11-04 — bounded shared dictionary latency and correctness

See [the report](../reports/v010_bounded_dictionary_speed.md) for scope and actual room counts. Final `2026-11-04-v010-reuse-headless-{4,8}floors` runs use L/XL, 120 max/floor, seed 123 and frozen source snapshots; each includes one real policy update and a separately timed independent preview. `reuse-final-4floors` was measured with a browser renderer active and is retained separately. No learning/convergence claim follows from one update.

`sampler-matched` compares only the proposal component on identical 480-node graphs at pinned commit `3e9ed018`, not whole episodes. `latency-audit-before/after` are instrumented profiles on different reached graph sizes, not matched throughput ratios. `bounded-dictionary-4floors` contains a failed XL overlap audit; the normalization regression fixes it. `bounded-dictionary-first` has an explicitly incomplete source snapshot. Development and corrected snapshots remain preserved. `bounded-site-audit` aborted on JSON serialization of site metadata; `bounded-site-audit-02` retains six ANY/FREE correctness smoke cases. These are not held-out convergence studies.

## 2026-11-05 — angle/length comparison

`2026-11-04-v010-angle-study-02` is the corrected completed 1,116-case pilot. Three initialization seeds, 60 episodes per strategy, ANY/FREE changing sites, four floors/120 maximum modules per floor. All initial/final geometry audits and failures are retained. Analysis and learning curves distinguish the common eight-site monitor from final 24-site validation. `angle-study-01` is complete but superseded by numeric-facet and invalid-start fixes; do not promote its results. Smoke and four-floor timing/profile directories are diagnostics, not convergence or matched whole-episode throughput evidence. [Report](../reports/v010_angle_proposal_evaluation.md).

## 2026-11-05 — individual hypotheses and gap audit

The `2026-11-05-v010-hypotheses-*` directories preserve the1,860-case ANY/FREE pilot, trained-checkpoint L/XL4/8-floor speed batch, frozen realizer/circulation checks,216 alternative rollouts,60 urban evaluations and696 post-hoc gap audits. Raw values/failed runs remain intact; geometry-check validity does not imply gap-free architecture.

`2026-11-05-v010-live-endgame-repair-01` is the authoritative exact-objective in-memory12-case/72-trial endgame diagnostic. `endgame-repair-01`/`02` retain export-reconstruction failures;01 overlapped tests and is not timing evidence,02 still has5 replay failures. Do not treat them as the live benchmark.

[Full report](../reports/v010_hypotheses_benchmarks.md). Research checkpoints have a separate schema; none replaced production weights.

## 2026-11-05 — continuity fix

`continuity-quality-01` is the216-case paired old/guard/closure comparison. `quality-02` rechecks72 final cases after support caching. `speed-02` is the final L/XL120max/floor4/8-floor,three-seed comparison; `speed-01` preserves the uncached measurement. `training-01` has36 ANY/FREE stochastic vocabulary episodes, one real update each and independent final audits. Final valid-start outputs have zero raw enclosed-gap area. Timing is not an equal-work speedup claim; the fix adds checking. `first-4floors` contains the superseded2.48m² failure. [Report](../reports/continuity_2026-11-05/README.md).

`continuity-live` records actual port8000 deployment verification after UI integration:
fresh9-floor UI inference and a separate694-reference WebSocket run,15 types,
zero raw enclosed gaps. Includes settings, full final event, independent polygon
union results and data/checkpoint preservation hashes. This is a smoke check,
not another speed or quality benchmark.

## 2026-11-05 — livable spatial proxy

Primary evidence: `2026-11-05-v010-spatial-quality-02` (72 paired changing-site training cases with minimum-fill guard), `spatial-speed-06` (final one-seed L/XL120max/floor4/8-floor check), and `spatial-verification` (337/20 test logs, live API/pause evidence, calibration). Quality01 preceded the fill guard; speed01 failed and speed02–05 retain superseded checker/frontage diagnostics. Lossless gzip preserves raw cases and source snapshots with uncompressed hashes. No fully spatial-feasible pilot outcomes or learning/throughput improvement are claimed. [Report](../reports/livable_spatial_2026-11-05/README.md).
