# Whole-edge glazing, graph prediction and plot conditioning — v0.10.0

2026-11-05. Branch `version/v0.10.0`.

## User requirement

Every livable module needs at least2m of glazed frontage, scaling as2m per15m² above15m²: `2 * max(1, area/15)`. Cores need no glazed frontage. Each entire facade edge is designated glazed or solid; there are no fixed opening slots or trimmed2m strips. Two glazed edges conflict if any pair of points is less than25m apart inside either edge's outward60° cone (±30°), with the other facade facing the source. At exactly25m the separation passes. Blank walls are not privacy targets.

## Graph training

`graph_spatial.py` reads the embedded graph and shared implicit prototypes, including their approximate areas, scalar supports/frontage, poses, contact evidence and vertical scopes. It constructs no floor polygons and places no windows. Numeric sky/exposure sampling remains a proxy and is performed at episode completion or explicit evaluation, not every action.

`graph_window_proxy.py` assigns **directional frontage budgets**. Opportunities describe an estimated outward direction, scalar frontage and estimated facade location. A vectorized pairwise uncertainty envelope inflates cone angles and reduces estimated separation by half-edge extents; these estimates are not exact window geometry. Selected opposing directions stand for likely glazed facades, so every blank facade is not automatically a privacy conflict. The bounded two-order allocator is a reference feasibility estimate, not a learned window designer or an infeasibility proof. The placement policy learns from the resulting terminal deficit.

The old facade-depth score is retained only as a separately named sky/facade diagnostic. The former `graphMinRoomExposure` does not determine window feasibility. `windowFrontageRatio` and `windowFrontageDeficit` report the new estimate; `unknownWindows=True` remains explicit during training. The objective identifier is `shared_constraints_v6_window_proxy`.

Void quality is separate: narrow-facing frontage or poor-sky-facing frontage contributes a crevice fraction across **all occupied functions**, including solid cores. Deleting windows or relabeling a room as core cannot hide it. The4m narrow-width threshold, .25 vertical-sky share and .05 allowed bad-frontage fraction are configurable research assumptions, not regulations. Existing fill/program/core/access constraints remain.

## Realization

`realized_spatial.py` measures actual polygon edges and independently checks contacts/occlusion using ray/segment intersections. It coalesces collinear subdivisions, marks an entire edge solid if it cannot serve as exposed glazing, and calls `graph_windows.py` only after realization. The finite three-order allocator designates whole edges glazed/solid. It never trims or resizes an edge to hit the area requirement. Analytic cone-distance checks include edge endpoints and oblique cases; midpoint/origin distance alone would be insufficient.

This validator is conservative: intervening opaque screens do not discount otherwise conflicting glazed edges. Thus a pass proves absence of the internal cone conflict, but a failed allocation is not proof that no feasible allocation exists. Glazing height/transmittance, materials, physical daylight/sun and outside-context window locations remain unmeasured. Do not label this environmental compliance.

Graph estimates are retained before realization, with absolute errors and threshold disagreements available separately. Actual frontage never replaces the training target. Equal shared footprints can have different glazed/solid fit-outs; `glazingPatternVariants` reports these separately. Footprint reuse is not fabrication/glazing reuse.

## Principal parcel directions

`plot_directions.py` retains measured boundary edge axes (including all three triangle directions) and uses exact polygon-area second moments for the long axis/aspect ratio. It is invariant to subdividing an edge. Eight rotation-relative direction descriptors feed a trainable encoder and actor; the continuous proposal head also receives the conditioned embedding. Optional site-direction proposals mix measured directions with observed or continuous lengths. Motif, closure and continuous proposals remain available. No rectangular template, mandatory grid, fixed-angle snapping or fixed bay lengths are introduced. `graphPlotDirections` provides an explicit ablation switch.

Graph checkpoint schema5 appends initially zero-influence direction heads; schema1–4 weights and Adam moments migrate without replacement. Existing opening/function heads remain trainable. Corridors can be internal to modules; no diagonal-access penalty or new corridor module is imposed.

Right angles remain a proposed **soft realizer preference**, not a hard graph constraint or default reward. No learned-quality improvement from that preference has been demonstrated.

## Exact performance changes

- Reject cuts that exclude compulsory graph junctions before attempting any shared-shape solve, using the existing witness/tolerance contract.
- Cache identical shared-shape constraint updates with required-contact sets included.
- Check each independently placed occurrence pair once, rather than repeating identical full-height contacts on every floor.
- Cache repeated contact proofs during growth; independent final checks deliberately bypass this cache.
- Reuse exact site-origin certificates across identical floor outlines and scope choices, keyed by complete loops/coordinates/radius without rounding.
- Pack unchanged policy feature calculations through numeric arrays rather than recursive tensor scalar conversion.

These change computation reuse, not search validity standards or prototype compatibility. Dense frozen comparisons and changing-site pilots are recorded in the accompanying report; finite pilots do not establish convergence or general performance.
