# Architecture pilot 01 — completed, inconclusive

2026-11-04, branch `version/v0.10.0`. This is a quality-screening pilot, not a convergence or engine-throughput claim.

Three architectures used one initialization seed (123), two training episodes, and the same two held-out sites evaluated before and after training: 18 episodes total. Every episode used ANY/FREE, auto-changing sites, four floors, and 120 allowed modules per floor. Failed geometry was retained. Site fingerprints were checked for paired identity. Frozen evaluation checks model hashes before/after every episode.

| Model | Allocated parameters | Valid held-out cases | Mean verified outcome | Actual fill | Independent-occurrence reuse | Change from untrained |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Pooled node MLP | 7,362 | 1/2 | -0.379832 | 32.972% | 78.914% | 0 |
| Global message passing (baseline) | 7,362 | 1/2 | -0.379832 | 32.972% | 78.914% | 0 |
| Local message passing | 9,410 | 2/2 | -0.300148 | 39.803% | 70.380% | +0.007985 |

The pooled control still allocates an unused message branch for checkpoint/initialization comparability; its active gradient-bearing parameter count is smaller. This is not a capacity-matched experiment.

The local variant's paired outcome difference is +0.079684, with an extremely wide pilot bootstrap interval [-1.126167, +1.285536]. Reuse decreased by approximately 8.53 percentage points. Both training episodes were invalid for every architecture, and one baseline held-out case was invalid due to a containment-mask bug. These data do not establish a better trained architecture. No model was promoted. The small pre/post change is real recorded output, not evidence of convergence.

## Artifacts

- `manifest.json`: exact protocol, old baseline commit and uncommitted runtime source diff, parameter counts and terminal run status.
- `runner_snapshot.py`: exact driver used for this run (before subsequent statistical-gate improvements).
- `sites.json`: held-out/training site coordinates, seeds and fingerprints.
- `episodes.jsonl`: every raw episode, including failures, independent geometry audit, optimizer updates, model hashes and measured areas/reuse.
- `summary.json`: pilot aggregates; promotion explicitly not performed.
- `*_seed123.pt`: actual trained graph checkpoints.

Command:

```bash
MODULE_LAB_DEVICE=cpu PYTHONPATH=src .venv/bin/python -u tools/compare_graph_architectures.py --output agent_notes/benchmarks/2026-11-04-v010-architecture-pilot-01 --seeds 123 --train-episodes 2 --eval-cases 2
```

To replay, copy the archived driver back to `tools/` so its repository-root discovery remains correct. The snapshot imports runtime code reconstructed from `4e171a35` plus the manifest's `workingDiff`. The subsequent containment fix is not part of this completed run. Pilot 02 tests that corrected mask separately. Later statistical gates use crossed seed/site bootstrap, require positive learning across seeds and constrain fill/reuse regressions. Pilot 01 cannot pass any such gate.
