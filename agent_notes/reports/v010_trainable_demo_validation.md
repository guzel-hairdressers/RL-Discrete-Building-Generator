# Trainable graph demo validation — 2026-11-04

Branch: `version/v0.10.0`.

- Full unit suite: 231 tests in 64.933 seconds, OK, skipped=2.
- Dedicated graph learner/oracle tests: 9 tests in 9.546 seconds, OK.
- Frontend production build: passed.
- Actual trainer integration verifies actor, critic and message encoder updates, persistent weights across sites, inference freeze, resumable checkpoints and corrupted-load rollback.
- The independent oracle contact tolerance rejects a 1 mm real gap while accepting nanometre-scale boundary roundoff.
- A small wiring smoke case completed with valid geometry and a recorded graph optimizer update. This is not a benchmark, convergence result, or held-out architectural-quality claim.
- The full demo was opened locally and its training controls exercised. UI values come from the live trainer; missing runtime data is not replaced with plausible constants.

No architecture has been selected as better than another. Comparative experiments are an active separate goal. Performance and quality comparisons must follow the repository's mandated workload/distribution protocol.
