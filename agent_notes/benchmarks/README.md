# Categorized Benchmark Results & Performance Ledgers

`agent_notes/benchmarks/`

This directory contains categorized, reproducible benchmark datasets, execution metrics, and visual evaluations for the **RL-Discrete-Building-Generator** (Module Lab).

---

## Directory Organization

```
agent_notes/benchmarks/
├── README.md                                          # Central Directory Index & Usage Guide (this file)
├── BENCHMARK_SUMMARY.md                                # Performance Comparison Matrix & Speedup Metrics
├── 26-08-10_v0.6c-legacy-baseline/                    # Baseline v0.6-c Python SAT benchmark datasets (Seed 808)
│   ├── historical_v0.6c_seed808_10ep.csv
│   └── historical_v0.6c_seed808_10ep.json
├── 26-08-10_v0.8.0-matched-speedup-eval/              # Matched speedup evaluation vs v0.6c (6.54x speedup)
│   ├── v0.8.0_seed808_matched_v06c_10ep.csv
│   └── v0.8.0_seed808_matched_v06c_10ep.json
├── 26-08-10_v0.8.0-stress-test-130modules/            # High-capacity workload evaluation (130 modules, Seed 123)
│   ├── v0.8.0_seed123_10ep.csv
│   └── v0.8.0_seed123_10ep.json
└── 26-08-11_v0.8.0-visual-grid-evaluations/           # Visual layout rendering grids & JSON floor plan layouts
    ├── v0.8.0_seed123_first3_grid.json
    └── v0.8.0_seed123_first3_grid.png
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
