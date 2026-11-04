# Graph UI contract — v0.10.0, 2026-11-05

This is the shared boundary between the backend agent and UI agent. The implementation is [server.py](../../src/server.py), [graph policy](../../src/graph_policy.py), and [protocol tests](../../tests/test_graph_hotpath.py). These are existing/additive fields, not a promise that proposed orthogonality/circulation features already exist.

## Commands and lifecycle

`/ws` accepts JSON commands. Preserve generationId and episode exactly as supplied by the server. `step` may advance several internal training steps; never assume one reply means one placement. Dispatch the next live graph step from the WebSocket callback; a zero-delay browser timer can be throttled in background tabs.

| Command | Required payload / behavior |
|---|---|
| updateSettings | settings object. Server validates it; consume the ack and following site event. Apply configuration edits together, not a stream of unintended restarts. |
| newSite / setSite | New site, or the selected siteId/city/tier/siteData. Use the returned generationId/episode. |
| setMode | mode: training or inference. Discards incomplete learning traces, preserves learned weights. |
| step | generationId, episode; step is telemetry, not an assumption about node counts. |
| evaluate | generationId, episode. Explicit geometry preview; does not update weights. |
| saveCheckpoint / loadCheckpoint | Preserve existing save/upload behavior. loadCheckpoint takes base64 fileData and can return migrated settings. |
| resetPolicy | Resets weights; keep distinct from resetting the camera or clearing a view. |

Training repeats episodes. Graph inference generates one layout and stops. Pause stops dispatch and accounts for an in-flight reply before requesting a fresh preview. Late/stale messages must not restart paused execution. Settings/site changes invalidate the current generation's pending messages.

## What each state means

- Live graph: type=placements, graphState.realized=false, placements=[]; dictionary polygons can be empty. Shared constraints exist even without polygon previews.
- Completed training: type=episodeDone, graphState.isComplete=true and realized=false. validation.status=not_run, valid=null; graphValid is a separate check. Do not equate completion with realized geometry.
- Explicit preview: type=placements, isEvaluation=true, graphState.realized=true. It can be a partial layout or the last completed training layout. policyUpdateCount is unchanged.
- Completed inference: type=episodeDone, complete and realized. Display validation.valid and unresolved/violations. An invalid layout is not a successful result because it is visible or has a positive score.
- completedEpisode/nextEpisode can refer to different layouts. Keep the inspected layout's episode separate from the next training episode.

## Identity, function, reuse

`graphState.nodes` carries id (floor reference), occurrenceId (independent physical occurrence), scope (independent or multi_floor), moduleId (shared geometric prototype), type (function), floor, orientation and position. Do not parse IDs to recover group membership. Graph positions are rounded for transport; realized placements.position preserves the origin. Realized rotation is in degrees; node orientation is in radians.

A multi-floor occurrence has several floor references, one footprint/pose/function and one occurrenceId. A geometric prototype can be used by different functions. Do not manufacture different module types from a core/room color distinction.

`metrics.reuseAudit` exposes prototypeCount, independentOccurrences, verticalCopies, singletonCount and independentRepeatFraction. The last is (N−K)/N across occupied independent occurrences. Holes and floor copies earn no independent reuse credit. confirmedReuseRatio is a different historical metric: fraction of occurrences belonging to repeated types.

Use moduleId for stable palette/highlighting. Per-prototype independent counts can be derived from distinct occupied occurrenceIds; generic dictionary.uses has legacy differences between graph and realized views. Never substitute floor-reference count for fabrication reuse.

## Estimates and metrics

- fillRatio: fraction, not percent. Show whether it is from graph constraints or realized measurements.
- rentableRatio: rentable / filled area; it is not site fill. Show area units explicitly.
- score can be a number or numeric string. It is an experimental composite, not architectural quality or legal compliance.
- moduleIdentityStatus=constraint_checked concerns shared definitions, not completed physical validity. confirmed/realized still requires validation.valid.
- unavailableMetrics and null mean unmeasured. Compatibility zeros for daylight/constructibility must not be presented as evaluated results.
- predictionErrors retains differences from realization. Do not rewrite prediction history with audited values.
- policyUpdateCount, gradientNorm and losses establish real updates, not useful learning. Label current versus last-completed statistics.
- episodeExecutionTimeMs is server-reported runtime; keep client wall time and postStepEvaluationMs separate. Do not invent fallback timing values or reset the episode clock on every batch.

## Current proposal settings

`graphProposalStrategy`: legacy (current default), continuous, vocabulary. The latter two are experimental. Keep generatorEngine and graphController controls. The current controller can be neural or reference.

`dictCap` is a soft target, default 10. `graphMaxTypes` is a hard ceiling, maximum 15. Incompatibility causes rejection, not forced merging. No angle-step/length-step constraint exists. Default learned continuous length bounds are 2.5–9 m through the size prior; observed values are measured, not snapped to integer bays.

`graphState.proposalVocabulary` reports observedLengthCount/observedAngleCount. Preview can include edgeLengths and relativeAnglesRadians. These are edge measurements, not module-type counts. Display radians as degrees only through an explicit conversion.

`selectedProposalSources` and `selectedFactorSources` describe completed decisions. The latter distinguishes observed/observed, neural/observed, observed/neural and neural/neural angle/length factors. Do not present old completed counts as the current in-progress episode.

There is currently no orthogonality-weight control, corridor-function policy, sunlight result, or guaranteed quality improvement to expose as a working feature. New backend fields will be additive; the UI should ignore unknown fields and tolerate absent optional fields.
