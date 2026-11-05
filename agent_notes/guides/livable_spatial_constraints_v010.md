# Livable exposure constraints and multiple-core actions — v0.10.0

2026-11-05. Branch version/v0.10.0. This supersedes the graph v4 objective where
only fill/reuse/program fraction contributed and exterior wells were unmeasured.

> Superseded for window/privacy requirements by [whole-edge glazing and graph proxies](whole_edge_glazing_v010.md). The original facade-depth target below is retained as historical evidence, not the current frontage requirement.

## What replaces the old daylight reward

The old6m-to-property-boundary score is not restored. The new quantity is a
**potential window-facade access proxy**, not illuminance, daylight factor, useful
illuminance, sunlight exposure or a compliance certificate.

Only `CellType.ROOM` is livable and has an exposure obligation. CORE, VOID and
BALCONY are excluded from its numerator and denominator. Any occupied module,
including a core, can obstruct a room. A room-to-core function change applies
atomically to the occurrence and every vertical copy without altering its shape.

For each room occurrence on each floor:

1. Use the shared prototype's graph-derived support constraints and pose. Sample
   numeric boundary intervals at an explicit physical spacing. No room polygons,
   Voronoi realization, clipping or Boolean overlay are created during training.
2. Cast outward directions against nearby occupied modules' implicit constraints.
   Shared-wall contacts provide no potential windows. Proximity relations remain
   separate from construction and access edges; they never shrink prototypes.
3. Estimate clearance and the unobstructed fraction of a **vertical sky slice** in
   that direction. Obstruction height and floor elevation matter. Higher-floor
   overhangs contribute their actual angular band, even if absent on this floor.
   Union overlapping bands rather than double-counting occlusion.
4. Qualified frontage must meet both configured clearance and sky-share minima.
   Multiply its physical length by sky share. For a room of areaA, the proxy is
   `min(1, skyWeightedQualifiedLength * daylightDepth / A)`. This is a facade/area
   depth allowance, not a point-by-point interior illumination calculation.
5. Evaluate room deficits against the configured target; aggregate by livable
   area only. Keep every room's evidence and explicit prior-boundary provenance.

The model currently represents a finite30m obstruction horizon and generated
building masses. External urban context shadows, windows, glazing, materials,
climate/sky luminance, reflected light and window-to-window sightlines are missing.
These limits remain explicit in the independent audit and UI. Physical lighting
simulation needs those inputs; see [Radiance](https://www.radiance-online.org//about)
and [EnergyPlus daylight calculations](https://energyplus.readthedocs.io/en/latest/guides/engineering-reference/7.1-daylighting-calculations.html).

## Requirements and optimizer

The spatial score uses explicit feasibility tiers rather than additive rewards
for facade count, void labels, core count or node count. Basic invalid graph
completion returns-1. A spatially infeasible graph receives a graded negative
return based on its largest normalized requirement deficit. Spatially feasible
completions receive a positive monotone transform of the existing design score.
Therefore extra fill/reuse cannot buy off a violated requirement.

The existing design score retains fill, residential share, independent reuse and
visible dictionary/singleton/underfill costs. The new requirements cover:

- Livable facade access, excluding cores from the obligation.
- Estimated shortest access distance to a core on the metric contact graph.
- Minimum residential share, preventing all-core relabeling.
- Configurable core area/width eligibility and aggregate served livable area.
- Minimum occupied site fill, preventing a tiny exposed patch from winning merely
  by satisfying the other requirements. This is additional to soft underfill cost.

Temporary gaps/disconnections are allowed while building. Completed requirement
failure is exported, not silently repaired, stretched or relabeled into a success.
Independent geometry validity and overall `designValid` are separate fields.

Access is still a room-contact-graph estimate: center/origin-length paths through
rooms are not a validated public-circulation plan, interior travel measurement,
stair layout or regulatory egress analysis. Explicit unit/corridor/door semantics
remain work beyond this implementation. Core capacity is a configurable area
budget, not a staircase engineering calculation or an allocated evacuation model.

## Configurable research assumptions

These defaults are design experiments, not building regulations or validated
architectural thresholds:

|Setting|Default|Meaning|
|---|---:|---|
|graphSpatialEnabled|true|New constraint objective and function choices; false retains v4 baseline|
|graphFacadeClearance|4m|Minimum clearance for qualified potential window frontage|
|graphMinSkyShare|0.25|Minimum visible fraction of the vertical sky slice|
|graphDaylightDepth|6m|Facade capacity/depth allowance|
|graphMinRoomExposure|0.35|Minimum room facade-access proxy|
|graphMinResidentialShare|0.65|Minimum livable fraction of occupied area|
|graphMinFill|0.40|Minimum occupied site fill for spatial feasibility|
|graphMaxAccessDistance|30m|Maximum estimated graph path to a core|
|graphMinCoreArea|12m²|Core area assumption|
|graphMinCoreWidth|2m|Core minimum-width assumption|
|graphCoreCapacity|500m²|Aggregate livable area served per eligible core,per floor|
|graphExposureHorizon|30m|Finite obstruction search horizon|
|graphExposureSampleSpacing|1m|Physical frontage sampling interval|

Principal thresholds are exposed under advanced configuration. Inputs are finite,
validated numbers, and changes rebuild the site transactionally. There is no
angle grid, equal-size rule or special square core introduced here.

## Policy and reuse

Growth now offers room/core function choices for full-height placements, as well
as promotion of existing eligible full-height rooms when access/capacity evidence
indicates need. Core count is not fixed or directly rewarded. Independent rooms
remain placeable; automatic new core shafts currently span all floors, consistent
with the released full-height scope. Arbitrary partial-height shaft/duplex systems
are not implied.

The policy receives six additional candidate relation/function features, including
local projection clearance evidence, graph access distance, footprint/frontage
ratio, served demand and building height. A projection gap is only a feature; it
is not treated as an exact minimum facade distance. The terminal requirement uses
the more complete implicit support-ray measurement.

A zero-initialized spatial head preserves old logits on checkpoint migration.
Graph learner schema4 adds that head and extends Adam parameter groups while
retaining existing weights/moments. Old policies remain loadable warm starts,
but their previous architectural objective differs; loading is not evidence they
already satisfy the new requirements. The public atomic role-change API still
supports joint core relocation. Automatic paired relocation/demotion is not yet
a new learned action in this implementation.

## Evaluation and runtime

Full exposure measurements occur at training completion, explicit pause preview
and inference completion. Per-action inputs use bounded local relation features;
no full exposure ray sweep is run for every candidate/action. Caches key on shared
prototype identity, pose, function and local neighbors, covering remote reused
occurrences and floor copies. Grouped NumPy slab reductions avoid thousands of
tiny per-object calls. Proximity never becomes traversable access.

The independent check uses realized polygon edges and ray/segment intersections,
with an independent point-inside test for overhangs. It validates the **same proxy
under realized geometry**, not physical daylight accuracy. Predictions and errors
are retained separately; inference/preview displays the measured proxy.

Numerically collinear fragments are coalesced for sampling on both paths. Rounded
bins were insufficient: near-equal normals could land on opposite bin boundaries
and duplicate potential window frontage. The corrected interval union uses actual
normal/bound tolerances and canonical projection. Realized footprints, occupied
areas and geometry audit tolerances are unchanged.

## Pause timing

Client elapsed time sums active intervals. Pause, disconnected idle periods and
paused geometry previews are excluded; resume continues the same episode clock.
Completed chart records use that accumulated active time. Server execution time
independently sums actual step work, including its finishing work, without counting
idle time between WebSocket requests. Geometry preview duration remains separate.
A regression simulates1s work,60s pause/preview,2s resumed work and records3s.

Evidence, failures, benchmark scope and unfinished quality gates are in the
[validation report](../reports/livable_spatial_2026-11-05/README.md).
