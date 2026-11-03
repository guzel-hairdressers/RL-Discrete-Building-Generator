# v0.10.0 trainable graph demo — 2026-11-04

## Start

```bash
.venv/bin/python src/server.py
```

Open http://localhost:8000, open Settings, click **Trainable graph demo preset**, close Settings, then click **Train**. The preset selects the graph engine, neural controller, a rectangular M site, four floors, and 16 modules per floor. This is a demonstration configuration, not a throughput benchmark. Diagnostics shows the graph algorithm name, cumulative weight updates, decision count, real losses/gradients, and completed geometry validity. The graph controller can be switched back to Reference search. Inference runs the same graph network greedily without changing its parameters or optimizer.

## Actual learning path

`src/graph_policy.py` implements a separate PyTorch graph actor-critic: 8-dimensional node features, a 32-wide message-passing encoder with two rounds, a candidate actor conditioned on pooled graph state and 10 proposal features, and a graph-level value baseline. Training samples feasible candidates using a session-local Torch generator. It does not imitate the reference-search ranking. The current actions choose placement proposal and single-floor/full-height scope; automatic role relocation/void planning is still future work.

At episode completion the learner applies discounted terminal returns (gamma .99), detached value-baseline advantages, smooth-L1 critic loss (coefficient .5), entropy regularization (.01), and gradient norm clipping (2). Learning rate follows the existing setting. An empty/no-decision episode reports zero updates instead of manufacturing a gradient.

The provisional training outcome is the graph score divided by 100 for independently validated completed geometry, or -1 for invalid completion. Raw score, `validation`, `geometryValid`, and `trainingReward` are retained separately. This is an experimental objective, not calibrated architectural quality or evidence of convergence. Environmental proxies are not optimized.

## State lifecycle

Site changes/settings changes discard incomplete tapes but preserve learned weights. Switching training/inference discards incomplete tapes. Reset Weights resets both learners. Save/Load includes graph model, Adam state, update count, and sampler RNG in an optional `graphLearner` payload; older checkpoints without it start a fresh graph learner. Checkpoint validation prepares the graph learner separately before atomic commit.

The graph encoder/actor/critic are separate from the legacy polygon policy, whose initialization RNG and checkpoint schema remain compatible. Extra graph initialization uses an isolated RNG context. Predictions and geometry do not receive gradients: this is score-function policy training, not differentiable polygon optimization.

## Numerical and UI correctness

Local half-plane solves are memoized; repeated equivalent rotations and repeated full-height evidence are deduplicated. No preset rectangular core is introduced. The independent contact oracle tolerates 1 micrometre of floating-point boundary noise; a regression case checks that a real 1 mm gap does not become a contact. The source polygons are not repaired or clipped.

The completion audit is captured before graph teardown; it is used by the actual training outcome and returned to the client. Online dictionary updates publish inferred prototypes instead of leaving the initial legacy swatch on screen. Live diagnostic fields retain the last completed learning signal while the next graph grows. Hardcoded UI throughput/action-count/memory figures and reward bonuses are removed from the demo; displayed reward terms match the graph objective.

## Verification and limitations

Network tests verify actor, critic and message-encoder parameter changes, frozen inference, no fake empty updates, seeded checkpoint sampling replay, weights preserved across new sites, actual server save/load, corrupted checkpoint rollback, mode-switch tape cleanup, and numeric contact tolerance.

Passing these tests proves wiring, not an improved architecture or learned generalization. The current network is a baseline. Architecture comparisons must use common settings and held-out seeds, actual geometry validity/area/reuse, and retained raw results. Quality evaluation uses ANY/FREE with auto-changing sites; throughput evaluation uses L/XL, 120 max modules per floor, 4–8 floors. No architecture winner is claimed yet.
