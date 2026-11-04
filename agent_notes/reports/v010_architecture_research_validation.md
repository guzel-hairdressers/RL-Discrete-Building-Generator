# Architecture research validation — 2026-11-04

Branch: `version/v0.10.0`. Latest full suite: 264 tests in 17.956 seconds; OK, skipped=2. The duration describes one test execution and is not an engine throughput result.

Coverage added:

- All four architectures backpropagate, checkpoint with their architecture identity, and preserve old schema-1 baseline loads.
- Local embeddings distinguish attachment nodes for otherwise equal proposal features.
- Candidate attention is invariant within tolerance to a rigid rotation/translation of the graph and candidates, and has real attention-weight gradients.
- Changing architecture resets the graph learner; changing sites preserves it. Local checkpoints load into baseline sessions without a silent subsequent reset.
- Invalid geometry cannot outscore the modeled range of valid negative outcomes after the bounded return transform.
- Concave-site vertex inclusion is insufficient: an edge crossing a notch is rejected. An independent GEOS oracle agrees on sampled oblique convex hull fixtures.
- Statistical helpers reject pilot promotion, retain failed cases, require actual paired sites/initializations, track before/after learning, and reject underfill-based or non-learning wins.

Completed empirical evidence: `../benchmarks/2026-11-04-v010-architecture-pilot-01/README.md`. This run is explicitly inconclusive. Pilot 02 was interrupted for the graph hot-path rewrite and remains incomplete. Neither wiring tests nor pilot 01 establish an architecture winner.

Current training uses graph-only rewards; historical geometry-gated pilots are not comparable to this environment. No candidate has been promoted.
