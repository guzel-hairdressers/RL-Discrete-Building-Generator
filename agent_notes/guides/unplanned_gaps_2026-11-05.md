# Unintended gaps between repeated modules — 2026-11-05

The user supplied a realized-layout screenshot with small triangular/polygonal
spaces between modules. These are architectural defects, not automatically
legitimate courtyards. The renderer's `displayPolygon` applies floor translation
only; it does not inset or shrink the supplied polygons.

## Why the current model permits this

Ordinary, unmodified Voronoi cells partition their domain. The current model is
different: it intersects neighborhood evidence across repeated occurrences, caps
the shared prototype with a size prior, then applies the same prototype rigidly
at all occurrences. A cut needed at one occurrence can remove a corner at another.

The solver proves non-overlap and a minimum positive contact length for required
connections. It does not prove that the union is a continuous, gap-free floor plate.
Three or more modules may share wall intervals while leaving an empty region
between their wall ends. Unused connection facets can become unintended internal
facades. Global filled area charges only the small missing area; that does not
represent the practical severity of a narrow, inaccessible leftover space.

The original `validation.valid` only covers its documented geometry/access
checks. It must not be presented as complete architectural validity. Public
circulation, unplanned gaps and actual door design are additional requirements.

## New independent audit

`layout_gaps.py` detects enclosed holes in the occupied union, subtracting only
predefined site holes and explicitly modeled void footprints. It reports number,
area, largest area and approximate largest inscribed diameter. A 0.01 m² reporting
threshold excludes numerical dust; it is not a courtyard-design standard.

A 1e-6 m diagnostic seam closing prevents floating-point cracks from hiding a
large unintended hole. It does not modify output footprints, geometric validity,
credited area, or shared shapes. A separate radius-based morphological diagnostic
estimates narrow exterior crevices; it can respond to benign concave corners and
is not yet a hard validity rule or a calibrated width metric.

The regression example fills 32 of 36 m² (88.9%) and has a 4 m² unintended central
gap. It fails the enclosed-gap criterion despite high fill and no overlaps.
Marking that entire region as an explicit site hole/void exempts it; merely placing
a small void inside a larger unintended gap does not exempt the rest.

The hypothesis study's raw results remain intact. The screenshot prompted a
**post-hoc** gap audit, reported separately; this was not secretly part of the
training objective. Original geometry-check passes are not gap-free-layout passes.

## Fix direction, not yet implemented

Require continuous floor-plate junctions, except explicit designed voids, as a
completed-layout acceptance condition. A useful graph-stage proxy should inspect
embedded cycles and shared contact-interval endpoints, rather than reward only
pairwise contact and total area. Compatible contacts must close interior junctions;
one wall may legitimately serve multiple neighbors, so this is not a requirement
for a rectangular grid or one neighbor per complete wall.

Keep module shapes shared and rigid. Do not independently stretch occurrences,
paint gaps over in the renderer, create one-off filler types without counting
them, or relabel every leftover gap as a courtyard. Revising placements and jointly
inferring compatible prototypes/ports is allowed; the final independent audit must
still check the actual union. Benchmark any additional local junction checking
before making it part of every training step.

The current orthogonal-cut realizer only removes material. It cannot fill an
existing gap, even if it improves a corner statistic. The oracle port adapter
reconstructs its supplied reference evidence; it is not an end-to-end solution
to the gap problem. These limitations take precedence over attractive fill scores.

## Subsequent implementation

Generation-time connected contact arcs and protected shared junctions now prevent these enclosed gaps. Endpoint proposals retain fill. See [current fix and measurements](../reports/continuity_2026-11-05/README.md). The earlier diagnosis/planning above describes12abf74d; the active-demo integration remains pending.
