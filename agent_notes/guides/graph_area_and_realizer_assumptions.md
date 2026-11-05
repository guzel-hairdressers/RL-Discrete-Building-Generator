# What graph-stage area means

The current graph stage carries **implicit geometry**, not connectivity alone.
Each shared prototype is a bounded intersection of linear inequalities in its
canonical frame. Every occurrence uses that same shape under rotation/translation.
The origin is persistent and need not be the centroid.

For example, `x <= 3`, `-x <= 3`, `y <= 2`, `-y <= 2` define a 6 × 4 m rectangle
with area 24 m². General prototypes use arbitrary observed normals. In the current
midpoint adapter a displacement d supplies `d.x <= |d|²/2`, after transforming
the displacement into the prototype frame. An explicit radius prior supplies
otherwise missing boundaries.

`graph_dictionary.make_shape` obtains the feasible interval on every support line.
For normalized normals and support distances b, the area is
`A = 1/2 * sum(b_i * length_i)` over active facets. This is the boundary-integral
formula for a bounded convex region; it constructs no polygon vertex list. Area
is shared across occurrences, including vertical copies. Voids earn no filled or
rentable area and no fabrication reuse credit.

This still costs work: solving support-line intervals is quadratic in the number
of candidate planes, and a changed shared shape can require checking contacts at
many occurrences. Caching/redundant-plane pruning reduce that cost; removing GEOS
or collision polygons does not make those checks free. "Graph-only training"
means no complete floor-plan realization/Boolean overlay during training, not
"only checking connectivity" or "no geometric calculations."

The computed area is precise for the current bounded convex half-space model,
within numerical tolerance. It is **not** an intrinsic area determined by an
abstract graph, or a calibrated estimate for every possible future realizer.
The numeric area prior must not be described as observed boundary evidence.

## Changing realization

A different realizer can infer different boundaries/areas from the same metric
graph. The right-angle preference therefore belongs to realization experiments,
not a bonus on arbitrary incident-edge angles. The frozen prototype experiment
changes one prototype jointly across its occurrences and measures contact/fill
loss rather than distorting instances independently.

The current growth dictionary itself uses midpoint separation/contact equations.
Replacing only the final rendering/realization function would leave those growth
assumptions in place. A genuinely replaceable adapter must also own its projected
constraints/contact tests and area prediction contract, with independent final
geometry audits and preserved prediction errors. The explicit-port experiment
tests such a boundary representation, but uses reference wall evidence; it is not
yet a trained port-generation system.

## Fill reporting correction

The 2026-11-05 hypothesis batch preserves its original source and raw statistics.
Its verified `actualFill` is the mean of exact per-floor ratios. Additional
`derived_exact_fill.jsonl` reports ratio-of-sums exact fill, gross plot coverage
and residential plot coverage without rewriting those raw measurements.

A live-path inconsistency was found while answering the user's fill question:
graph training/preview use the legacy count of raster cells as their denominator,
whereas independent validation uses exact site polygon area. The correction is
kept separate from the controlled batch so no experiment changes definitions
halfway through. Final implementation/status is recorded in the study report.

The live correction is now implemented: all graph fill paths use exact net polygon
area, and independent helpers use ratio-of-floor-area-sums fill. Mean-floor ratios
remain separately available. Preview/inference also expose independent spatialQuality
gap diagnostics; this does not repair the generator's floor plates.
