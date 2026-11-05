# Graph constraints and legacy objective audit — 2026-11-05

Status: implementation decisions and isolated correctness probes. The live trainer,
reward, model weights and UI have not been changed by this audit.

Current checkout: version/v0.10.0 at076ae57e. Historical source inspected directly:
main73f473aa (2026-08-26,v0.9.0) and version/v0.9.0-alpha0dc53ded (2026-09-13).
The branch retains an alpha name; this is a source reference, not a proposed version
or branding change. Legacy notes were used to locate intent, not accepted as proof
of throughput, quality or convergence.

## What the old objectives were trying to do

These are provisional architectural preferences in code, not established standards.
Legacy src/server.py line references below are at0dc53ded.

| Concern | Historical mechanism and intended purpose | Decision for graph generation |
|---|---|---|
| Occupied fill | +80 times fill; extra35-point underfill deficit below40%. Prevent sparse or prematurely stopped designs. | Keep occupied fill, distinguish residential/site fill; re-evaluate redundant shaping without removing pressure to fill. |
| Residential efficiency | +15 times residential/occupied area and -15 times core/occupied area. Reduce nonrentable space. | Program constraints before efficiency optimization. Additional cores/corridors must not be bought away to maximize the room label. |
| Daylight | +25 times residential samples within6m of the property boundary. Actual exposed-envelope distance was separately reported but not used for this term. | Do not port. Site proximity is not access to a usable facade and ignores facing obstruction. |
| Deep interior rooms | Dijkstra distance from rooms with exposed edges, seeded by centroid-to-edge distance, then accumulating room-center distances. Progressive penalty beyond4.5m. | Preserve the concern; use room-to-qualified-open-space exposure/depth evidence, not light propagation through neighboring rooms. |
| Opposing facades | One outward midpoint ray per exposed segment,5m range, severity-weighted length; skip segments shorter than0.8m. Terminal cost min(30,3*mean weighted length/floor). | Restore the design requirement with subdivision-invariant graph/dictionary evidence and an independent realized check. Old thresholds are configuration history, not adopted privacy/daylight requirements. |
| Minimum crevice | Candidate rejection for1.2m midpoint clearance; acute shared-vertex angular rule below45degrees. | Keep minimum usable open-space widths where applicable; discard fixed-angle rule and fragile midpoint/bbox implementation. |
| Access and cores | Core cluster area24m², spacing, room-crossing limit, path-to-core and30m graph travel limit. Mixed action rejection and terminal penalties. | Restore configurable functional requirements and explicit access routes. Treat completed failure as invalid, with temporary construction disconnection allowed. No universal24m² or30m requirement inferred from old code. |
| Partial wall contacts | Small penalty on partial connections, plus strict1:1/1:2/2:1 edge-length matching in candidate validation. | Usable contact/opening constraints and shared prototypes already give meaningful checks. Do not restore length-ratio catalogue; aligned partial contacts can be legitimate. |
| Shape regularity | +2 times regularity weighted by triangle fraction; -8 per average unmerged triangle/floor. | Do not port shape-family bias. Manufacturing widths, corner quality or joint complexity need their own explicit realizer/fabrication settings. |
| Equal module areas | Up to15-point dictionary area coefficient-of-variation cost. | Drop blanket equal-size preference; heterogeneous rooms may need different sizes. Use program and admissible module-size bounds instead. |
| Compact envelope | +1 times4*pi*occupiedArea/exposedPerimeter². Intended to discourage sprawl. | Diagnostic or explicit configurable envelope cost after calibration; do not force circles/compact blocks at the expense of usable courts and facade access. |
| Reuse/BPE | +2 times reuse plus capped30-point reward for repeated merged occurrences across floors. | Keep confirmed independent prototype reuse, already implemented; no vertical-copy or hole credit. No reward for merging operations themselves. |
| Uniform usage entropy | Up to2 points for evenly distributed module counts. | Drop: uniform usage is not required for economical reuse, and competes with a dominant useful module. |
| Dictionary excess | Squared cost, episode-dependent multiplier5→20,capped80. | Keep visible stable soft budget plus hard compatibility/type ceiling; no forced matches and no hidden episode-dependent architectural objective. |
| Frontier/time | Up to4-point relative-frontier score with small-piece adjustment. Despite name relativeTimeReward, this ref uses frontier change; wall time is telemetry. | Keep runtime as an external benchmark; do not pay for perimeter/frontier count that can favor branches or fragmentation. |
| Diversity | DPP bonus computed/reported at finish. It was not added to the score or shared floor targets at this revision. | Keep alternatives selection separate from validity/objective. A reported field is not necessarily a training signal. |

Legacy reward path: terminal_metrics lines3228–3343; aggregate lines5183–5343;
per-floor target lines5346–5395; finish lines5883–5983. Per-floor scores feed the
placement learner; global score also feeds building/shape decisions. Inspecting
only the metric dictionary would misidentify some training objectives.

## Reproduced old weaknesses

`probe_legacy.py` extracts the exact old functions via AST, retains function hashes
and executes them in isolation. It also confirms those functions match August
main. Run with the project's venv Python; no old server, datasets or policy run is
started. These are small correctness probes, not performance benchmarks.

1. Two12m facing facade segments3m apart produce9.6 weighted occluded metres.
   Subdivide the identical faces into0.5m pieces: the metric becomes0 because all
   pieces are skipped. This demonstrates representation-dependent scoring, not an
   observed trained exploit.
2. Two4x4m rectangles1m apart pass the intended minimum1.2m clearance validator.
   Its nearby list is filtered by overlapping bounding boxes with1e-6 tolerance;
   the opposing rectangle is removed before ray testing. This isolates that
   validator; it does not claim this pair forms a complete legal building.

[Raw outputs](probes.json). The hard1.2m rule and5m terminal chasm measure were
separate mechanisms, so a missed hard rejection could still incur terminal cost.
The old depth-to-air calculation also counted any qualifying exposed edge as air:
an edge facing a dark narrow slot could seed its own apparent daylight access.
This follows code inspection; no daylight accuracy benchmark has been performed.

## A graph-only proxy for the wells

An unembedded connectivity graph cannot determine clearance. The existing
representation is an embedded metric graph with origins, orientations and shared
prototype constraints. These supply scalar extent estimates without realizing
polygons. This is implicit geometric evidence, not purely combinatorial inference.

Add a separate **open-space proximity relation** between nearby same-floor occupied
occurrences, including pairs that have no construction/contact/access edge. Those
pairs often form the opposite banks of a slot. Never turn a proximity relation
into a traversable doorway or into midpoint evidence that shrinks the modules.

For directionu between origins, retain directional extents inferred from each
prototype. A cheap projection screen is

    g_proj = dot(origin_j-origin_i,u) - h_i(u) - h_j(-u)

whereh includes each occurrence's rotation. Positiveg_proj gives a separating
projection gap, hence a lower bound on Euclidean footprint distance. Small or
negativeg_proj does NOT prove a narrow facing gap or overlap: oblique footprints
can have overlapping projections while remaining separate. It must not be used
alone as a hard invalidity test.

A centerline alternative uses radial extents derived from numeric inequalities:

    rho_i(u) = min(b_k / dot(n_k,u)) over positive denominators
    g_ray = originDistance - rho_i(u) - rho_j(-u)

This measures a particular origin-line gap, not the minimum facade clearance;
it can miss narrow off-axis corners. Both screens use cached numeric dictionary
constraints. Neither requires a Voronoi solve, room polygon export or Boolean
operation. Existing Shape.support provides the projection operation.

Refine only potentially risky pairs using directional/contact support intervals,
checking opposing exposure, tangential overlap, third-room obstruction and gaps
along the overlapping interval. Integrate over physical extent rather than count
facets; merge equivalent adjacent interval evidence so subdivision cannot change
the answer. Shared contact intervals are excluded from open-air separation costs;
uncertainty or an unobserved boundary cannot earn exposure credit automatically.

Connect the resulting free-space sectors in an auxiliary evaluation graph to
estimate narrow-slot width, bottlenecks and depth to a genuine open mouth. These
are metadata, not placed void modules or fabrication/reuse credits. This still
needs an explicit sector construction and calibration; gap width alone does not
determine how far the slot runs. Never assume every path toward the site boundary
provides a useful open mouth.

Track width distribution, maximum severe deficiency and affected residential
exposure separately. Average widths or exposed-perimeter normalization alone can
hide a bad slot by adding wide courts or extra facade. Add obstruction height/
width and floor elevation as separate context features. These are daylight-access
risk indicators, not illuminance or verified privacy. Windows are not modeled.
Known context buildings must eventually enter obstruction evidence too.

## Where constraints should act

- Completed layouts: explicit minimum usable clearance/exposure and circulation
  requirements cannot be compensated by fill/reuse. Missing evidence remains
  unresolved, rather than silently passing a prior-based estimate.
- Intermediate growth: expose risks to the actor and cheap candidate screening;
  do not reject every temporarily narrow gap, since later modules may fill it.
  Apply hard rejection only for certified irreparable violations or at completion.
  Avoid a blind rule that permanently prevents two fronts joining.
- Policy representation: current default message passing follows construction
  graph edges and edge lengths, with coarse candidate features. It has no explicit
  opposing-space relation or width/depth input. Add relational/candidate features,
  rather than expecting a new terminal penalty to teach an invisible distinction.
- Search: proposals can respond to measured slot risk without fixed rectangular
  motifs. Additional bounded proposal work must be measured, not assumed cheap.
- Final independent evaluator: actual exposed boundaries, opposing clearance,
  slot depth, shared openings, access distance and uncertainty errors. Run only at
  preview/inference/validation, preserving graph-only training.
- Optimization: retain a small transparent objective for fill, functional/program
  efficiency and independent reuse; use other quantities as constraints or
  diagnostics first. A future constrained optimizer still needs calibrated
  measurements and constraint-specific reporting; it does not remove proxy errors.

## Multiple cores: representation versus actual policy

The release generator currently seeds exactly one full-height core in
server._step_graph_voronoi. GraphDictionary.commit always creates CellType.ROOM.
The neural actor therefore has no automatic additional-core choice, although the
model supports several cores and atomic whole-occurrence function reassignment.
Current access validity only requires reachability to some core; it does not
impose travel/capacity requirements that make an additional core necessary.

A core must remain a function of a valid placed module, not a special hardcoded
square. Add policy choices for room/core function, scope, and atomic reassignment
or relocation. Full-height scope is currently one footprint/function over its
floors. Shape identity must survive function changes. Core count should follow
configured functional constraints: usable core dimensions/capacity, access distance
on explicit circulation, served demand and required route redundancy where chosen.
No claim of regulatory compliance is implied by these modeling settings.

Reachability through a chain of private rooms is not a public circulation plan.
Add public circulation/unit membership before presenting travel checks as usable
apartment access. Prefer shortest paths on explicit access edges with distance
estimates; exact interior travel distance needs entry/exit ports or equivalent
room traversal evidence. Center-to-center length is only a graph estimate.

Do not impose one core per fixed number of rooms, award core count, or universally
penalize each extra core. Nonresidential area is an efficiency tradeoff only after
requirements are met. Temporary incomplete access remains allowed during growth;
completed layouts must pass. Initial-core placement is currently a site-preparation
choice, not a learned relocation decision. Automatic multi-step core planning and
role decisions are implementation work, not already enabled by the action API.

## Implementation and validation order

1. Add open-space relation/evidence cache and independent completed metrics.
2. Calibrate on current held-out outputs plus adversarial straight/tapered slots,
   wide courts, shallow notches, oblique facing rooms, split boundaries, nearly
   touching corners, deliberate courtyards, context buildings and partial growth.
3. Add policy features and required function/circulation/core actions. Keep each
   ablation separate from adding a new terminal objective.
4. Gate completed feasibility with configured requirements; compare cautious
   candidate screening to end-only constraints. Quantify termination/fill failures.
5. Only add soft environmental optimization where prediction errors and rankings
   justify it; retain every failed run and separate graph versus realized errors.

Cache by prototype revision and pose; invalidate neighborhoods for ALL occurrences
of a changed shared type, including remote/floor copies. Search radius must cover
module extent plus clearance/obstruction horizon, not just contact neighbors.
Avoid all-pairs rays or whole-floor recomputation for each candidate.

Throughput comparison must useL/XL,120maximum/floor,4–8floors. Quality/learning uses
ANY/FREE auto-changing sites plus held-out urban boundaries. Report wall time,
reached occupied area/fill, failure rate, spatial constraint errors, types,
independent reuse and core/circulation statistics. Small hand fixtures above cannot
establish throughput or learning improvements. No such benchmark was run here.
