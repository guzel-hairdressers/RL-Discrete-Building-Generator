# v0.10.0 shared-graph implementation verification — 2026-11-03

Branch: `version/v0.10.0`, based on experimental parent `62cc27e8`.

- `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_*.py'`: 222 tests in 33.299 seconds; OK, skipped=2. This duration describes one test execution, not engine performance.
- Thirteen new shared-prototype/action/evidence tests and three evaluator-accounting tests cover rotation/reflection, complementary evidence, incompatible-budget matches, full-height geometry, hole semantics, role rollback, containment without clipping, coincident seeds, algebraic growth, contextual sun rays, relabel/rotation invariance, overlap rejection, failed case retention, and raw error separation.
- Legacy tests were revised to remove fixed core-area assumptions, mocked labels as equivalence evidence, elapsed-time correctness limits, and fill clamping that concealed invalidity. Existing exact core-stacking tests were retained unchanged.
- `npm run build` in `frontend/`: passed. Existing unrelated frontend changes and generated distribution artifacts are not included in this implementation commit.
- Selective implementation diff whitespace check: passed.

No throughput benchmark, RL convergence run, or genuine held-out proxy-accuracy study was performed. The earlier desktop manifesto is not validation evidence. See `../guides/shared_graph_v010.md` for incomplete stages and calibration gates.
