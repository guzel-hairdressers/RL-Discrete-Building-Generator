# v0.10.0 trainable graph demo — 2026-11-04

Run `.venv/bin/python src/server.py`, open http://localhost:8000, select the graph engine and neural controller, and use Train or Inference. Training and inference share learned weights. Inference stops after one realized layout; training repeats episodes. Architecture selection uses `graphPolicyArchitecture`; message passing remains the default. No architecture winner or convergence result has been established.

## Training and the shared dictionary

Training never calls the polygon adapter, rasterizer or GEOS validator, including at episode completion. It maintains a `GraphDictionary`: stable prototype identities, shared canonical half-space constraints, required contact intervals, and grouped full-height occurrences. Added observations may refine one shared shape, but must preserve every required contact at every occurrence. A conflicting proposal is rejected. Preview and inference convert those same definitions to polygons, without reclassification, clipping or per-occurrence resizing.

The dictionary has a soft target (`dictCap`, default 10) and a hard ceiling (`graphMaxTypes`, default/maximum 15). Hitting the ceiling does not merge incompatible rooms. A run can stop with `no_compatible_placement`, before the room limit or desired fill. This is an unresolved growth/search limitation, not a completed packing certificate.

Node positions are proposed at continuous angles and distances conditioned on the current graph/site. Existing observed contacts also supply transformed placement proposals. There is no grid, fixed turn set, square-core template, or predefined architectural pattern catalogue. The actor chooses among compatible position/prototype/orientation and independent/full-height scope proposals. Patterns must arise from those decisions and shared constraints. Continuous pose refinement, automatic function/core relocation and hole planning are not trained actions yet.

The objective `shared_constraints_v4_reuse` is `tanh(graph_score/100)` when graph access and conservative site/size checks pass, and -1 otherwise. The score contains:

- 80 × fill fraction, capped at one, and 15 × rentable fraction.
- **20 × (N − K) / N** for independent module reuse, where N counts occupied independent occurrences and K their shared prototype types. Full-height floor references and holes earn no additional reuse credit. Provisional legacy star labels earn none.
- Visible soft budget, singleton, underfill and access penalties. Hard constraints cannot be bought off with reward.

Every decision receives the same undiscounted completed-design return. Discounting a negative terminal outcome previously made delaying that same failure appear better. Detached advantages, smooth-L1 critic loss (.5), entropy regularization (.01), and gradient clipping (2) remain. Real gradients and reward wiring do not establish useful learning or architectural quality; changing this objective requires fresh controlled learning evaluations. Existing weights remain loadable but were trained under earlier objectives.

## Work during growth and preview

Incremental spatial queries replace all-room proximity scans. Candidate work is bounded and redundant constraints use cached scalar support. Shared half-space support intervals determine area using `0.5 * sum(support_distance * facet_length)`, without constructing vertices. This is an exact area for the selected bounded convex model within numerical tolerance, not a claim that the model captures all architectural requirements. The explicit 64-direction size prior is still reported when it supplies boundaries.

Site/hole checks are scalar radius-clearance certificates. They are conservative and can reject feasible perimeter rooms. Neighbor midpoint inequalities prevent overlap in the implicit model; both sides' surviving scalar intervals must provide the configured contact length. Physical containment, overlap and contacts are audited independently after realization. Environmental performance remains uncalibrated and excluded from reward.

The WebSocket `step` runs a training burst of at most 16 internal steps or approximately 75 ms (one indivisible step can exceed that window), then sends the latest snapshot. Inference advances one step per request. The viewer caches label textures and static scene setup instead of rebuilding them for every graph update. Pause is serviced between bursts and requests a separate geometry preview.

Training returns `geometryValid: null`, `validation.status: not_run`, and a separate `graphValid`. Shared implicit identities have `moduleIdentityStatus: constraint_checked`; physical validity remains unmeasured until preview/inference. Preview preserves weights, optimizer and update count. Subsequent training reads implicit areas and assignments rather than cached realized geometry.

## Lifecycle and evidence

Site/settings/mode changes discard incomplete tapes and preserve weights. Save/Load retains model, Adam, architecture, update count and sampler RNG. Invalid loads roll back. Historical checkpoint `siteId` migrates to `realSiteId`; site events synchronize controls.

See the [bounded dictionary and latency report](../reports/v010_bounded_dictionary_speed.md) for L/XL 120-per-floor, 4/8-floor timings, actual reached counts, the retained failed overlap run, and limitations. See [architecture evaluation](graph_architecture_evaluation.md) for the separate research gates. The suite checks polygon-free training completion, shared rotations, incompatible types, near-parallel constraints, full-height footprints, independent reuse credit, real gradients, preview isolation, and checkpoints. No throughput ratio is inferred from unequal episode lengths.

## 2026-11-05 — observed factors and UI contract

The per-building angle/length vocabulary and a learned continuous proposal head are now experimental options via graphProposalStrategy. Mixed proposals can reuse a length while inventing an angle, or reuse an angle while inventing a length. Old checkpoints migrate to schema 3. No angle/length increment is imposed.

The corrected three-seed pilot does not demonstrate faster learning; legacy remains default. See [measured results](../reports/v010_angle_proposal_evaluation.md), [implementation guide](relative_angle_vocabulary.md), and [UI contract](../contracts/graph_ui_v010.md). The independent identity/reuse exports are additive and do not affect rewards. Right-angle preferences and explicit corridor policies remain proposed experiments.
