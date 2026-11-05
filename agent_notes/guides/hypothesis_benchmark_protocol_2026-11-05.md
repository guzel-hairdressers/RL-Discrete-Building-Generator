# Individual hypothesis benchmarks — 2026-11-05

Branch: `version/v0.10.0`. Default behavior is unchanged. The UI checkout is owned
by the separate UI task; this work only adds opt-in backend research hooks.

The user corrected the orthogonality proposal: treat 90-degree corners as a
realizer preference, not a graph-edge-angle objective. This study follows that
separation. A different future realizer need not inherit midpoint bisectors.

## Experimental matrix

| Hypothesis | Implemented ablation | What the measurement can establish |
|---|---|---|
| Boundary/goal conditioning | Actor/critic context receives intrinsic local boundary segments, nearest corners, holes, site scale and fixed objective descriptors. Equal parameter-count control receives zeros; new output layer starts at zero. | Paired held-out fill/outcome and early learning benefit for boundary inputs under the fixed goal. Changing user preferences/general budget conditioning still requires training on varied goals. |
| Rank before checking | Online logistic feasibility ranker, trained only on training checks; four compatible plans sought before selection, with continued fallback scanning if none fit. | Time/check savings versus the opportunity cost of a smaller feasible choice pool. Not a feasibility replacement. |
| Local repair | At most six trials per episode, two at a trigger; free local displacement/rotation of low-degree occurrences; transactional full implicit rebuild; accept only a higher unchanged objective. | Whether this bounded reference repair earns its copy/rebuild cost. Not a learned move/reassign policy or an optimized incremental repair kernel. |
| Orthogonal geometry | Frozen shared prototypes; free wall-derived orientations with continuous refinement; bounded rectangular cuts at 0%, 2%, 10% maximum area loss. Preserve origins, identities and all required contacts; independent validation. | Right-corner/fill/contact/runtime tradeoff for this conservative realizer experiment. Does not prove arbitrary shape synthesis or justify graph-angle snapping. |
| Explicit circulation | Post-layout connected public corridor assignment; each remaining room is a private unit; realized positive-length openings, atomic full-height functions; 65% residential program threshold. | The area/program cost hidden by room-through-room reachability. Not a trained circulation-growth policy or a compliance assessment. |
| Contact ports | Convex adapter accepts explicit canonical wall/port planes pooled across occurrences. Frozen reference-wall evidence is marked oracle. Rotated oblique corridor correctness fixture has several rooms on one straight corridor wall. | Adapter capability and reconstruction latency; not better generated layouts, since a learned port predictor is absent. Non-neighbor containment/overlaps remain independently checked. |
| Site certificates | Radius check first, then support-halfspace/segment certificate for candidate shape. Includes holes and concavities, without room polygons in training. | Valid perimeter fill recovered versus extra checking cost. The initial full-height prior still needs a certified origin. |
| Alternatives archive | Deterministic frozen layout plus three categorical samples, same reward and validity. Retain near-best valid candidates under a declared coarse topology descriptor. | Quality/alternative-count versus additional inference time. No diversity reward or learning-speed claim. |

## Quality and learning

- ANY/FREE, auto-changing sites, 120 maximum occurrences per floor, four floors.
- Three initialization seeds 123/456/789; paired training sites and 24 held-out
  evaluation sites; 60 training episodes per arm/seed, milestones 0/20/40/60.
- The common first eight held-out sites are used for learning curves. Initial and
  final checkpoints evaluate all 24. Failed layouts retain outcome −1 and
  valid-adjusted fill zero. No held-out feasibility labels train the ranker.
- This is a pilot, not a convergence claim. Full 750-episode confirmation and
  untouched irregular urban sites are required before a quality default changes.
- Training never calls the realizer; final frozen evaluation does. Model digests
  and update counters prove frozen evaluations do not update either model.
- Report outcome/fill, residential area, independent reuse/types/occurrences,
  failures, reached floor references, and both episode-count/wall-time curves.
- The boundary experiment holds goals fixed; its data cannot establish varied
  budget/preference generalization. The current generator's free-site distribution
  is not a substitute for a held-out urban-site confirmation set.

## Speed

L and XL, 120 maximum per floor, four and eight floors, three paired seeds.
Store every step duration/reached size and all repair trial times/results.
Setup, graph rollout, auxiliary model update and independent realization/audit
are separate. Measure full episodes and check/placement costs; fewer reached
rooms/lower fill do not count as an improvement. Where paths differ, do not
label episode-time ratios as equal-work speedups. Run the throughput batch
without other agent-launched heavy benchmarks/tests.

The quality pilot's wall times include normal desktop load and an overlapping
unit-suite run in its first initialization. They are descriptive learning-time
observations, not isolated engine throughput. The separate speed study is the
primary performance evidence.

## Reproducibility and adoption

Every run stores settings, seeds, source snapshots/hashes, revision, raw episodes,
failures and checkpoints. Experimental checkpoints have an explicitly separate
schema and never replace the user's production checkpoint.

Use paired, crossed bootstrap intervals across initialization seeds and held-out
sites. Show per-seed effects and changes from each arm's own untrained policy.
Multiple exploratory comparisons and three seeds limit certainty. No automatic
promotion; a plausible effect must survive confirmation and the independent
geometry/program checks.

## Observed limitations and follow-up corrections

The original repair selector used an aggregate surrogate, not the exact per-floor
objective, and spent its trial budget early. Raw pilot data retain that implementation.
The corrected selector and live endgame benchmark are separate. The screenshot-prompted
gap audit is explicitly post hoc; original geometry validity did not include continuity.
Exact-area denominator/aggregation corrections followed the controlled batch. See the
[measured report](../reports/v010_hypotheses_benchmarks.md); no quality default was promoted.
