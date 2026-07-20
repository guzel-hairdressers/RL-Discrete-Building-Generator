# v0.6-C Core Stacking and Site Adaptation

> [!CAUTION]
> **TEMPORARILY UNSUPPORTED / DO NOT EDIT**
> `rl_v0.6-c` is currently marked as **temporarily unsupported**. Please do not edit or modify files in this directory.

## Physical invariant

With `singleFloor: false`, every Core placement belongs to exactly one building-wide stack. For a stack `S` and every floor `f`, the committed placement satisfies:

```text
moduleId(f, S) == moduleId(0, S)
rotation(f, S) == rotation(0, S)
localAnchor(f, S) == localAnchor(0, S)
localPolygon(f, S) == localPolygon(0, S)
```

World-space polygons remain offset in the visualizer so floors can be seen side by side. The invariant is deliberately evaluated before those viewport offsets.

## One action, one atomic commit

Independent floor candidate generation excludes Core modules. The trainer instead constructs `CoreStackCandidate` records from one shared transform and calls the ordinary exact-vector candidate validator on every floor. This checks:

- containment in every outer boundary;
- exclusion from every atrium;
- collision against every floor's existing placements;
- core spacing and legal edge contact; and
- every floor's module cap.

Every shared candidate's placement features are pooled equally across floors and scored once in a building-level categorical. When independent room actions are also legal, that categorical includes one pooled `no-stack` branch; floor-specific room categoricals are sampled only if it wins. A selected Core therefore has exactly the log-probability of the physical building action that is propagated, rather than `floorCount` duplicate or vote-selected terms.

The transform is revalidated immediately before commit. Environment states are snapshotted, and an unexpected commit error restores all floors. A stale candidate that is blocked on only one floor therefore changes no floor. Building-level decisions report `triggerFloor: null` and `decisionScope: "building"`.

## Boundary and atrium adaptation

Generation computes a square reserve large enough to contain every fixed Core polygon under arbitrary 2D rotation, plus 4 m of room-growth clearance on each side.

1. A half-metre search finds one exact local reserve anchor inside every original outer loop.
2. If none exists, all floors switch together to their existing axis-aligned envelopes and the search is repeated. Width, height, and overall extents are not enlarged; using one explicit building-wide fallback avoids a mixture of silently adapted and unadapted constraints.
3. Atrium candidates are generated against the adapted boundaries. Any candidate intersecting the common reserve is removed before central or learned selection.
4. The final reserve is checked against every built site's outer loop and selected holes.
5. If no legal reserve can be guaranteed, generation raises `CoreStackingError` before `_commit_generation`; an existing session keeps its prior valid generation.

The reserve persists for the site. Before terminal learning or reset, every selectable next-episode primary Core (with that episode's exact rotation phase) is preflighted on empty floor environments. The learned dictionary can only select from this proven superset, and its recorded initial-candidate count is taken from that preflight before the episode state is committed.

The fixed vocabulary is first filtered by every polygon's actual edge lengths and vertex count (`1–9m`, at most the active `3–8` edge cap). The mandatory first Core and Room dictionary slots are then sampled from an edge-compatible subset using the placement engine's 1:1, 1:2, and 2:1 wall rule. If no compatible multi-floor seed remains, the settings transaction fails before site preparation or current-generation mutation. This preserves learned selection within the legal subset while guaranteeing that the locked first anchor has a room-growth interface.

## Protocol metadata

`site`, `placements`, and read-only evaluation events expose a top-level `stacking` object. Multi-floor online and terminal metrics expose a compact `coreStacking` object; canonical single-floor mode omits it.

An `episodeDone` event pairs completed `placements` and `mergedPlacements` with the completed `dictionary` and `mergedDictionary`. Its separately prepared `nextDictionary` becomes active only at the `nextEpisode` transition.

Important fields include:

- `status`: `ready` or the single-floor disabled state;
- `mode`: `original-boundaries` or `envelope-fallback`;
- `reserve`, `reserveAnchor`, and `placementAnchor` in local coordinates;
- `adaptedBoundaryIndices` and rejected atrium candidate IDs;
- `stackCount`, `lockedCoreCount`, and `exactLocalAlignment`;
- each stack's shared ID, module, rotation, anchor, building decision scope, nullable legacy `triggerFloor`, and per-floor placement IDs.

Each public boundary also includes local reserve metadata plus `worldReserve` and `worldPlacementAnchor` for rendering.

## Scope

v0.6-C synchronizes Core modules only. Room and corridor geometry continues to optimize independently per floor after the locked anchors are installed. Turning on `singleFloor` disables the structural Core/Corridor roles, core-dependent topology checks and metrics, the shared action coordinator, and boundary reserve adaptation.
