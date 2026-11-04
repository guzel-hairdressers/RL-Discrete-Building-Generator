# v0.10.0 trainable graph demo — 2026-11-04

Run `.venv/bin/python src/server.py`, open http://localhost:8000, select the graph engine and neural controller, and use Train or Inference. Training and inference share learned weights. Graph inference stops after one realized layout for inspection; training continues across episodes. Architecture selection is available through the `graphPolicyArchitecture` setting/API; the message-passing baseline remains the default.

## Training versus realization

Training is graph-only, including episode completion. It does not call the shared polygon solver, Voronoi adapter, rasterizer or GEOS validator. Geometry is created at inference completion or on explicit evaluation/preview (including Pause). Previewing a completed training graph preserves the learner's parameters, optimizer and update count. Training resumes with fresh graph estimates, ignoring cached preview geometry and its audit.

The actor chooses candidate placement and independent/full-height scope. A two-round message-passing encoder, candidate actor and graph value baseline are trained with discounted terminal returns (gamma .99), detached advantages, smooth-L1 critic loss (.5), entropy regularization (.01) and gradient norm clipping (2). Empty episodes report zero updates. Automatic role relocation, hole planning and continuous pose refinement remain unimplemented policy actions.

The experimental reward is `tanh(graph_score/100)` for layouts passing graph access and conservative size/site checks, and -1 otherwise. It uses no realized validity or area. Training returns `geometryValid: null`, `validation.status: not_run`, a separate `graphValid`, and `trainingObjective: experimental_graph_proxy_v2`. Null means unmeasured, not valid. Inference and preview return independent geometry audits. No gradients pass through the evaluators.

## What graph mode checks and estimates

A spatial index supplies local neighbors. One full-height occurrence pools distance constraints across every floor. Contact intervals are computed algebraically on the bisector under both occurrences' pooled constraints. Adding a node refreshes affected contacts on every relevant floor and removes occluded old edges. A conservative inscribed-radius bound accounts for the convex adapter's finite prior directions.

Site masks use scalar point/segment clearance, including static site holes. A radius-clearance certificate is sufficient but conservative: a feasible perimeter placement can be rejected. Core origins are prepared from continuous site-conditioned proposals; no fixed core polygon is synthesized by the legacy policy. Graph initialization bypasses legacy shape-policy sampling and polygon core preflight.

Area uses cached angular quadrature of implicit distance constraints, with 24 samples and intrinsic orientation. Its accuracy is uncalibrated. Provisional module descriptors are hypotheses, not confirmed shared prototypes; they earn no confirmed fabrication-reuse credit. Dictionary-budget and singleton estimates remain visible and provisional. Environmental metrics remain unavailable. The fast evaluator is not yet equivalent to the shared-prototype solver, particularly for complementary partial module evidence.

Realization solves the building once, shares that result across floors, and validates unmodified placements. A prototype merge must preserve the overlapping contact interval between both placed rooms, not just a long enough face on each individual module. Site holes, overlaps, containment and actual access are checked independently. Preview reports prediction errors without replacing graph predictions or feeding them back into training.

## Lifecycle and evidence

Site/settings changes discard incomplete tapes and preserve weights. Mode switches discard incomplete tapes. Reset Weights resets both learners. Save/Load retains graph model, Adam state, architecture, update count and sampler RNG. Schema-1 graph checkpoints load as the baseline; invalid loads roll back atomically. Checkpoints from UI site switching accept the historical `siteId` alias and migrate it to canonical `realSiteId`. Site events synchronize the restored configuration with the UI controls.

The suite checks zero realization through an entire training episode, real gradients, frozen inference, pause/preview isolation, checkpoint replay, full-height evidence, contact occlusion and static-hole containment. Wiring tests do not demonstrate convergence. See [architecture evaluation](graph_architecture_evaluation.md) and [graph-only runtime validation](../reports/v010_graph_only_validation.md). No architecture winner or calibrated graph/geometry correlation is claimed.
