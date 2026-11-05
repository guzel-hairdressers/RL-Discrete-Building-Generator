# Livable spatial requirements — implementation and validation

2026-11-05,version/v0.10.0. Implemented graph/dictionary potential-window access,
multiple-core actions, feasibility-tier training, independent realized checks,
UI diagnostics/configuration and pause-aware elapsed timing.

**Only livable ROOM occurrences require daylight access.** Cores have no daylight
obligation and cannot dilute the livable-area denominator. They remain obstructions.
No polygon realization/Boolean operations were added to graph training.

[Implementation contract and configurable assumptions](../../guides/livable_spatial_constraints_v010.md).

## What is established

- 337 backend tests complete successfully,2 skipped;20 frontend protocol tests pass;
 production bundle builds. Tests include core exemption/obstruction, narrow wells,
 floor height, overhangs, continuous rotation, remote shared-prototype cache changes,
 numeric seams, collinear aliases, shape-preserving full-height role changes,
 checkpoint migration/new-head gradients, preview metrics and anti-thinning.
- Live WebSocket verification performs one actual policy update and creates7
 independent core occurrences. Graph training has `validation.status=not_run`;
 separate preview passes geometry/gap checks with zero raw enclosed-gap area.
 Spatial requirement failure remains visible; geometry validity does not imply it
 passed the architectural proxy requirements.
- Client timing regression:1s active+60s paused/preview+2s active records3s.
 Server work-clock regression independently excludes idle between step requests.
 The live check inserts2s idle and confirms it is excluded from execution time.

## Proxy calibration is geometric, not photometric

The final72 changing-site cases plus8 dense cases contain10,738 room-floor
references. Independent polygon-edge measurement of the same proxy agrees with
the implicit-support prediction: mean absolute error1.95e-6,p95 3.05e-9,max0.01087.
Per-floor maximum error is0.000181. No room changes side of the configured0.35
threshold in these cases; rank agreement is recorded with raw results.

These statistics do not establish physical daylight accuracy. Windows, materials,
climate/sky luminance, reflected light, external-context shadows and explicit
window-to-window privacy are missing. The finite-horizon vertical sky slice and
facade/area depth allowance remain explicit research approximations.

[Calibration data](../../benchmarks/2026-11-05-v010-spatial-verification/calibration.json)
can be regenerated with `tools/analyze_graph_spatial.py`.

## Finite training pilot: no convergence claim

Paired baseline/new arms,3seeds x12 episodes,ANY/FREE auto-changing plots,4floors,
120maximum modules/floor,target10/hard maximum15. Every case performs one real
optimizer update; preview afterward is frozen and cannot affect that update.
Six named checkpoints preserve the two arms for each seed. All failed outcomes
are retained. The exposure, function-action and objective changes are a combined
package; this is not an attribution study for each individual component.

|Metric|v4 baseline|New constraints/functions|
|---|---:|---:|
|Cases|36|36|
|Geometry+enclosed-gap checks pass|36/36|36/36|
|All spatial requirements pass|0/36|0/36|
|Mean occupied fill|42.57%|45.29%|
|Mean reached floor references|112.4|117.8|
|Mean worst spatial deficit|0.3605|0.3236|
|Mean independent cores|1|4.47|

The pilot does **not** demonstrate that the trained network reliably produces
acceptable buildings, or that it learns faster. Its average tradeoffs are
preliminary; different sites make first-versus-last episode comparisons invalid
as learning evidence. Long held-out learning evaluation, including750episodes,
is still open. The all-failure spatial result is not presented as success.

Primary raw evidence:
[quality02 manifest](../../benchmarks/2026-11-05-v010-spatial-quality-02/manifest.json).
Quality01 preceded the explicit minimum-fill guard and remains preserved.

## Dense workload check and runtime limits

Final exposure implementation was checked atL/XL,120maximum/floor,4and8floors,
seed123,with both arms and an actual graph-only optimizer update per case. All8
outputs pass independent geometry/gap checks; none passes all spatial requirements.
Mean rollout is4.90s baseline versus5.79s new,with421 versus471 reached references.
Mean fill is52.75% versus50.17% for these four paired workloads. The8-floor XL
new case reaches805 references in12.23s versus743 in10.41s for its control.

These are unequal-work,one-seed descriptive measurements, not speedup ratios.
Desktop host load varied significantly during the broader studies, so precise
throughput or learning-speed claims are unwarranted. Earlier runs contain severe
host-load outliers and are retained. Quality timings overlap verification work
and are not used as isolated speed measurements.

[Dense06 manifest](../../benchmarks/2026-11-05-v010-spatial-speed-06/manifest.json).
The later minimum-fill guard changes feasibility feedback, not the frozen initial
placement sequence in this dense check. Final-default quality02 includes that guard.

## Failures retained and fixed

- Speed01 failed because a NumPy boolean could not serialize; fixed with explicit
 Python boolean output. Its trace is preserved; it contributes no successful case.
- The first polygon-edge checker missed rays starting inside an upper-floor
 overhang projection. Fixed with an independent inside test and a regression.
- Rounded normal bins could split nearly identical supports into different groups,
 duplicate frontage and overstate one room's proxy by0.46. Replaced with normal/
 offset comparisons, common-frame interval union and straight-edge coalescing.
 The offending graph is captured as a numeric regression; footprints and geometry
 audit tolerances were not changed.
- Preview initially omitted the new aggregate metrics, although the independent
 audit carried them. The production WebSocket smoke test caught it. Preview now
 exports measured proxy values and preserves prediction errors; its regression is
 in the suite. The initial failing event remains in verification artifacts.
- Core-only relabeling is prevented by residential-share requirements. A tiny
 exposed patch is prevented from becoming a successful completion by an explicit,
 configurable minimum-fill requirement, not by rewarding module/room counts.

Speed02–05 are superseded diagnostics. Their immutable source snapshots,settings,
seeds,rows and failed outcomes are retained as losslessly compressed artifacts.
No release quality assertion is based on their incorrect frontage measurements.

## Remaining scope

Public circulation/unit grouping, interior travel and actual stair capacity,
window placement/privacy, external-context shading, full sky/lighting simulation,
partial-height core systems, automatic paired core relocation/demotion and an
explicit free-space-mouth/depth graph remain future work. The public API already
supports atomic role relocation; the new learned path adds placement functions
and promotion rather than claiming all these actions are trained.

No remote push was made. Existing saved production policies are preserved; schema4
migrates their learned tensors/moments and starts the added relation head at zero
influence. Warm-start compatibility is not proof of meeting the new objective.
