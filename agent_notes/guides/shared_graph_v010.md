# v0.10.0 shared graph/prototype reference implementation

2026-11-03. Branch: `version/v0.10.0`. The v0.9.0 release remains unchanged.

## Implemented

`src/shared_modules.py` infers convex prototypes from midpoint half-plane constraints in canonical rotation frames. All floor observations of one full-height occurrence contribute to one footprint. Candidate groups pool complementary constraints; every required contact face must survive. A dictionary cap never forces equivalence. There is no reflection, per-occurrence clipping, resizing, fixed square core, or centroid recentering.

The size prior is explicit: default radius 4.5 m, area range 1–80 m², minimum contact length 0.5 m, 64 directions approximating an isotropic bound. These are modeling priors, not measurements or building-code requirements. Boundary evidence touching the size prior is reported. Settings `graphPriorRadius`, `graphMinArea`, and `graphMaxArea` expose the principal limits.

`src/graph_actions.py` provides rollback-safe attach, pose, and joint function-change actions. Attach requires an existing construction anchor. A full-height function change updates all floor references atomically. `BuildingGraph.reassign_functions(..., require_access=True)` checks same-floor construction access; completed geometry validation independently checks actual contacts/access. Holes are not traversable or occupied. Floor graph nodes are compatibility views grouped by root occurrence metadata; they are not independently realized.

The reference search performs reproducible one-action lookahead over continuous spatial proposals and motif translations. It explores single-floor and full-height residential additions. Role/pose edits, including explicit hole scaffolding and joint core relocation, are available through the action interface; automatic multi-action hole/core planning is not implemented. Balanced and alternatives modes share an objective; alternatives samples within 5% of the best candidate objective. There is no learned graph policy yet.

Graph construction uses algebraic local neighbor intents rather than constructing full Voronoi diagrams during growth. Intent edges are not physical-contact certificates. `missing_required_contacts` checks contact intervals during search; the independent GEOS oracle checks containment, overlap, contacts, access, and occupied union area at completion. A failed completion is exported as invalid, not repaired into apparent success.

## Metrics and inference limits

Area comes from canonical implicit convex constraints; this is cheap local geometric inference, not purely combinatorial topology. Graph metrics explicitly report `estimateStatus=uncalibrated` and prior/unresolved counts. Unavailable legacy scalar fields remain zero for client compatibility and are listed in `unavailableMetrics`. They are excluded from the reference objective.

The soft budget cost is `10*(max(0,K-B)/B)^2`; singleton cost is `5*S/N`. These are transparent provisional reference-search settings, not learned or calibrated reward weights. Independent occurrences and vertical copies are separate. Holes earn no fabrication-reuse credit.

`src/graph_evidence.py` supplies an uncalibrated angular/well-span daylight-accessibility estimate and a separate point-origin ray estimate conditioned on explicit sun directions and obstruction heights. Neither is illuminance or compliance. Sun directions/time/geolocation are not automatically inferred. Missing data remains missing. These environmental proxies do not contribute to reward before calibration.

`tools/evaluate_graph_proxies.py` accepts a JSON manifest with `split: held_out`, graph nodes/edges, and floor boundaries. It records every case, invalidity, absolute occupied-area error, pairwise ordering agreement, manifest, and revision. It currently evaluates area; environmental calibration is explicitly unavailable. No held-out accuracy or throughput result is claimed by this implementation.

Inference currently uses deterministic greedy class formation with candidate orientation enumeration. It does not yet retain multiple competing global partitions or perform beam/backtracking search. Conflicting partial evidence can therefore require future reassignment/search improvements. The Voronoi-compatible convex adapter cannot establish general architectural feasibility for arbitrary graphs. `realizer_unsupported` is an explicit outcome.

## Protocol and UI

Select Graph & Voronoi in settings; the legacy backend default remains `discrete_polygon` for compatibility. `graphSearchMode` accepts `balanced` or `alternatives`. UI mode selection needs a frontend rebuild.

The `/ws` command `applyGraphAction` requires current `generationId` and `episode` plus an `action` object. Examples:

```json
{"cmd":"applyGraphAction","generationId":1,"episode":0,"action":{"kind":"attach","id":"well","anchor":"core_0","x":10,"y":15,"scope":"multi_floor","function":"void"}}
```

```json
{"cmd":"applyGraphAction","generationId":1,"episode":0,"action":{"kind":"reassign","functions":{"core_0":"room","well":"core"}}}
```

Completed graph events include `validation` and `predictionErrors`. Prototype IDs are building-global within each solve; stable IDs across edits with changed partitions remain future work. Dictionary swatches are in actual canonical coordinates. Existing frontend local changes are preserved separately from this commit.

## Next gates

1. Benchmark/reference-search optimization only after correctness and failure-rate characterization on varied real sites.
2. Genuine held-out calibration for area, daylight and sun; retain invalid cases.
3. Multi-action beam/backtracking search, automatic void scaffolding and core-role/pose optimization.
4. Train a graph policy only after evaluator calibration; demonstrate parameter updates and held-out gains independently.
5. Concave/multi-part realization and cross-floor/duplex access are later proposals.

Do not cite the earlier desktop manifesto's speedups, convergence, daylight percentages, or forced vocabulary compliance as validation of this implementation.

Verification: [v0.10.0 validation record](../reports/v010_shared_graph_validation.md).
