# v0.8.0 core stacking

In a multi-floor run, a core is a building action rather than a floor action. A legal stack has one exact signature:

```text
(module id, rotation angle, local anchor x, local anchor y)
```

The signature is checked against every floor with the normal vector containment, raster, collision, and core-spacing predicates. World-space canvas offsets are deliberately excluded; equality is measured in each floor's local coordinate system.

## Site preparation

The design target is 4–8 playgrounds interpreted as stories; the default is
four and the core transaction suite exercises both four and eight. The backend
continues accepting the legacy 1–16 range so single-floor experiments and old
clients remain loadable. Changing `parallelEnvironments` through
`updateSettings` constructs and preflights a complete new generation before it
replaces the old one, so the story count can change safely between runs without
resizing a live episode or exposing a partial floor group.

The first learned core module is synthesized before an episode begins. Candidate anchors come from raster cells common to all original sites, then every proposed polygon is validated with authoritative vector geometry. If the intersection contains no valid transform, the complete floor group is discarded and regenerated with a new deterministic attempt seed. Individual floors are never swapped, boundaries are never enlarged, and irregular boundary families are never replaced with rectangles.

Preparation tries at most 24 whole-site transactions. Exhaustion raises `CoreStackingError` without committing the proposed generation.

## Policy actions

The mandatory first core has no no-stack alternative. Once all floors have their first locked core, the policy may choose between:

- one of the exact shared core transforms; or
- a building-level no-stack gate followed by ordinary floor-local room actions.

Core candidates are removed from every floor-local action list. A chosen stack pools its per-floor feature rows and creates one categorical log-probability term. It is not duplicated per floor.

## Atomic commit

The selected transform is revalidated immediately before mutation. Each floor then records a targeted checkpoint containing only placement-owned mutable structures: placement and adjacency indexes, occupied cells, module-use counters, spatial buckets, core IDs, attachment-frontier indexes, scalar areas, and done state. Immutable sites, boundaries, dictionaries, RNGs, and model state are not copied.

If any floor placement raises, every floor is restored from those checkpoints and neither the core-stack record nor its policy log-probability is appended.

## Protocol

`site`, `placements`, evaluation, and `episodeDone` events include `coreStacking`. Its key fields are:

- `enabled`, `status`, and `mode`
- `boundaryPolicy` and `siteResampleAttempts`
- `initialCandidateCount`
- `stackCount` and `lockedCoreCount`
- `exactLocalAlignment` and `violations`
- `stacks`, including the module, rotation, local anchor, floor/placement IDs, `decisionScope: "building"`, and `logProbTerms: 1`

Locked placement records also expose `coreStackId`, `coreStackLocked`, `coreStackTriggerFloor`, and `localAnchor`. `singleFloor: true` reports `status: "disabled-single-floor"` and produces no stack records.
