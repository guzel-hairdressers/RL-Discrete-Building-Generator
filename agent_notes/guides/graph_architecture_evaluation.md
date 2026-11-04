# Graph-policy architecture evaluation — 2026-11-04

The released demo's `message_passing` baseline remains the default. No architecture winner has been established.

## Experimental implementations

- `pooled`: per-node feedforward updates and global mean pooling, without edge messages. A control for whether the global GNN actually helps candidate decisions.
- `message_passing`: existing two-round graph encoder, pooled context plus ten proposal features.
- `local_message_passing`: adds the candidate's attachment-node embedding to its actor input, allowing different local neighborhoods to affect action scores.
- `candidate_attention`: adds candidate-conditioned attention over graph nodes, using signed relative position, distance and floor delta in the proposed action's local frame. No fixed compass/grid direction is imposed. Tested for gradients, frame invariance and checkpoint round trips; no quality experiment has evaluated it yet.

`graphPolicyArchitecture` selects the model through settings/API. Changing architecture creates a fresh learner explicitly; site changes preserve the existing model. Graph checkpoints store architecture/schema metadata and reject inconsistent settings. Schema-1 graph checkpoints remain loadable as the baseline architecture. Architecture selection does not alter geometry validity or dictionary equivalence.

## Fixed outcome and physical checks

The current training outcome is `tanh(graph_score/100)` for graph-valid completions, otherwise -1. Training never realizes geometry; held-out inference uses independent realized validity, union areas and module occurrence counts. These outcomes are distinct and retained separately. Historical pilots 01/02 used the earlier geometry-gated objective and must not be pooled with new runs.

The graph hot path uses scalar pooled contact intervals and cached area estimates. Module identities are provisional until shared-prototype realization. Full-height evidence propagates across floors. Site masks use conservative radius clearance, including static holes. Geometry confirmation remains separate from the learner. See [the trainable demo guide](trainable_graph_demo.md) for limitations and the exact mode contract.

## Comparison driver

`tools/compare_graph_architectures.py` uses ANY/FREE, four floors, 120 max modules per floor and a new site per episode. A fresh environment fixes generation counters for each site; the learned network persists across training episodes. Initialization seeds and site seeds are separate. All models must see identical site fingerprints. Each validation set is evaluated with frozen weights both before and after training. Raw errors and invalid completions are retained; missing/error results cannot improve an average through omission.

The outcome is reconstructed from independent occupied union areas, rentable union areas and independently placed prototype occurrences. Vertical copies do not count as separate independent occurrences. Recorded episode times are debugging context, not throughput comparisons between policies producing different layouts.

Promotion is never automatic. A validation candidate requires at least three initialization seeds and 24 held-out sites per seed, consistent positive paired improvement, a crossed seed/site bootstrap interval above zero, no extra invalidity, positive held-out learning from initialization, no more than 2 percentage points mean fill loss, and no mean reuse loss. It still requires untouched confirmation sites and protocol-compliant throughput testing. The default full training budget is 750 episodes; short pilots do not establish convergence.

Pilot command (screening only):

```bash
MODULE_LAB_DEVICE=cpu PYTHONPATH=src .venv/bin/python -u tools/compare_graph_architectures.py --output agent_notes/benchmarks/NEW_RUN --architectures message_passing local_message_passing --seeds 123 --train-episodes 12 --eval-cases 6
```

Each new output directory preserves the runner source, source diff, manifest, raw cases, site coordinates, checkpoint weights and summary. Completed pilot 01 is inconclusive; see its report. Pilot 02 was interrupted to prioritize the graph hot-path rewrite; its partial results and interruption are preserved. Do not combine their scores as though they used one environment version.
