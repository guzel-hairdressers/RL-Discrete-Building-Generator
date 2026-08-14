# Master Benchmarking & Across-Phase Metric Presentation Guide

`agent_notes/guides/benchmarking_guide.md`

This guide codifies the mandatory benchmarking execution protocol and metric presentation standards for **Module Lab** across all roadmap phases and performance optimizations.

---

## 1. Mandatory Across-Phase Benchmark Presentation Format

Whenever presenting multi-phase or progressive roadmap benchmarks, agents **MUST NOT rely purely on compounding totals**. 

Instead, benchmarks **MUST be presented as step-by-step isolated net deltas** alongside cumulative progress, with the final column reserved for **Impact & Evaluation**.

### Standard Across-Phase Markdown Table Format:

```markdown
| Metric | Clean Baseline (`<hash>`) | Phase 1 (PPO + GAE)<br>*(Net vs Baseline)* | Phase 1C (BPE Regularization)<br>*(Net vs Phase 1)* | Total Net Delta<br>*(Phase 1C vs Baseline)* | Impact & Evaluation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Mean Aggregate Score** | 36.9782 | 38.7944 (**+1.8162**, +4.91%) | 41.6277 (**+2.8333**, +7.30%) | **+4.6496 pts** (+12.57%) | Consistent, step-by-step reinforcement learning progress. |
| **Score Variance (StDev $\sigma$)** | 9.9727 | 8.8703 (**-1.1024**, -11.05%) | 8.6176 (**-0.2528**, -2.85%) | **-1.3551** (-13.59%) | **Major stability gain**: GAE and ratio clipping prevent policy oscillations. |
| **Mean Raw Geometric Score** | 18.5059 | 18.4358 (-0.0701, -0.38%) | 18.8162 (**+0.3804**, +2.06%) | **+0.3103** (+1.68%) | Regularized shapes produce cleaner, higher-density room plans. |
| **Rentable Area Ratio** | 0.8194 | 0.8237 (**+0.0043**, +0.52%) | 0.8246 (**+0.0009**, +0.11%) | **+0.0052** (+0.63%) | Stable, high-efficiency floorplate utilization across all stories. |
| **Site Fill Ratio** | 0.2570 | 0.2601 (**+0.0031**, +1.19%) | 0.2637 (**+0.0036**, +1.38%) | **+0.0067** (+2.59%) | Tighter boundary adherence without edge sprawl. |
| **Mean Placed Modules** | 41.0200 | 42.5600 (**+1.5400**, +3.75%) | 43.2000 (**+0.6400**, +1.50%) | **+2.1800** (+5.31%) | Agents sustain longer, productive placement trajectories before termination. |
| **Reused BPE Modules** | 8.7800 | 9.6600 (**+0.8800**, +10.02%) | 10.1600 (**+0.5000**, +5.18%) | **+1.3800** (+15.72%) | Anti-sprawl limits encourage recurring, reusable module patterns. |
| **Mean BPE Bonus** | 23.4000 | 25.2000 (**+1.8000**, +7.69%) | 25.8600 (**+0.6600**, +2.62%) | **+2.4600** (+10.51%) | Higher reward yield from discoverable multi-room assemblies. |
| **Episode Wall Time (s)** | 4.5063 s | 4.5891 s (+0.0827 s, +1.84%) | 4.5831 s (**-0.0059 s**, -0.13%) | **+0.0768 s** (+1.70%) | Mathematical regularization adds essentially zero wall time overhead. |
```

---

## 2. Table Column Requirements

1. **Column 1 (`Metric`)**: Full, descriptive metric name (Score, StDev $\sigma$, Raw Score, Rentable Area, Fill Ratio, Placed Modules, Reused BPE Modules, BPE Bonus, Wall Time).
2. **Column 2 (`Clean Baseline`)**: Mean $\pm$ StDev on the unpoisoned baseline anchor before any phase modifications.
3. **Columns 3..N (`Phase X`)**: Absolute value for that phase followed by **isolated marginal delta** and percentage change relative to the *immediately preceding phase* (i.e. $\Delta = \text{Phase}_{X} - \text{Phase}_{X-1}$).
4. **Second-to-Last Column (`Total Net Delta`)**: Total cumulative change from Baseline to the final Phase ($\Delta = \text{Phase}_{\text{Final}} - \text{Baseline}$).
5. **Last Column (`Impact & Evaluation`)**: Concrete, qualitative engineering analysis explaining the architectural or geometric driver of the observed delta.

---

## 3. Standard Benchmark Execution Command

For consistent, comparable results across phases:
```bash
python3 benchmarks/benchmark.py \
  --episodes 50 \
  --seed 123 \
  --json-out agent_notes/benchmarks/<date_experiment_folder>/<phase_name>_50ep.json \
  --csv-out agent_notes/benchmarks/<date_experiment_folder>/<phase_name>_50ep.csv
```
