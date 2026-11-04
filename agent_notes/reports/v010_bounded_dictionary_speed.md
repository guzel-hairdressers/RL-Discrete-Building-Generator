# v0.10.0: shared module limits, training latency and reuse reward

> Later numerical corrections and the angle-proposal experiment supersede this report for current behavior. Earlier timings remain raw evidence for their captured source revisions, not current performance claims. See [the corrected comparison](v010_angle_proposal_evaluation.md).

2026-11-04; branch `version/v0.10.0`. Parent revision `3e9ed018`. This report records implementation checks and latency smoke runs, not convergence or an architectural-quality result.

## What caused the slowdown and type explosion

The old graph path did not call polygon realization during training. Its remaining work was nevertheless expensive: exhaustive candidate enumeration, pairwise proposal deduplication, repeated all-node proximity scans, whole-building sketches rebuilt for each floor, and contact refresh across the building. An instrumented XL step near 300 nodes took roughly 204 ms: candidate sampling accounted for about 96 ms, sketches about 66 ms and contact refresh about 55 ms nested inside that work. These numbers overlap; they must not be summed. Raw profiles: `2026-11-04-v010-latency-audit-before`.

Strict quantized whole-neighborhood signatures also assigned hundreds of provisional types. They were not a shared module dictionary. Budget penalties could saturate the terminal tanh reward near -1, leaving little useful distinction between outcomes. Discounting the same negative completed-design outcome by the number of remaining actions additionally rewarded delaying failure.

The browser repeated static scene setup/camera/context work and appended override styles on graph updates. Its working renderer generated fresh label canvases/textures per node per frame. Those costs existed even though no floor-plan realization was requested.

## Implementation

`GraphDictionary` is now authoritative during generation and realization. Prototype IDs remain stable within a building. Neighbor midpoint evidence is pooled into shared canonical half-spaces. Required contacts must survive in both modules' scalar support intervals at every occurrence. New evidence can refine a shared module; all occurrences then use the same definition. Conflicts reject the proposal. A hard maximum of 15 types accompanies the existing soft target of 10; neither budget can justify assigning incompatible geometry to one module.

Growth uses spatial indexing, bounded proposals, indexed distance/orientation correspondence, cached support and immutable prototype arrays. Support-line integration measures the selected convex model's area without producing vertices. Inference/preview converts the same constraints to polygons and performs independent physical checks. Per-shape support caches and global constraint/plane caches are bounded for repeated training.

Training is still a genuine actor–critic choosing compatible position/prototype/orientation and vertical-scope proposals. Continuous proposals have arbitrary angles, supplemented by transformed contact relationships observed in the current layout. No fixed architectural pattern catalogue, Cartesian grid or prescribed turn set is supplied. This is candidate-based RL, not a network directly emitting unrestricted coordinates.

The reward now explicitly includes **20 × (N − K) / N** for shared-module repetitions. N counts independent occupied occurrences, K their prototype types. Holes and vertical copies do not increase this reward. Fill, rentable area, soft budget, singleton and underfill/access terms remain visible. Completed-design returns are undiscounted. The objective is `shared_constraints_v4_reuse`. Reuse wiring and gradients are tested; useful learned patterns remain a hypothesis requiring controlled training comparisons.

The WebSocket sends the latest snapshot after a bounded training burst (16 internal steps or approximately 75 ms, excluding indivisible step overruns). Inference remains one step per request. The viewer reuses type badge materials/textures, skips unnecessary dot geometry, and performs static iframe setup only when the site/view configuration changes. Realized geometry replaces the graph overlay on preview.

## Timing evidence and limits

Runs use CPU, L/XL rectangular sites, seed 123, 120 maximum modules per floor, and four/eight floors. Each starts with the same untrained network, completes one actual optimizer update, and times preview separately. Source snapshots, hashes, settings, reached counts and failures are retained. Reached instances include vertical floor copies; they are not independent reuse counts. All cases stop at `no_compatible_placement`, so they cannot establish throughput at a completely filled 480/960-instance workload.

| Final reuse objective | Reached floor instances | Types | Graph training | Separate preview | Valid preview |
|---|---:|---:|---:|---:|---|
| L, 4 floors | 266 | 15 | 1.04 s | 0.25 s | Yes |
| XL, 4 floors | 451 | 15 | 2.47 s | 0.68 s | Yes |
| L, 8 floors, repeat 1 / 2 | 437 | 15 | 3.48 / 2.97 s | 0.39 / 0.39 s | Yes / Yes |
| XL, 8 floors, repeat 1 / 2 | 806 | 15 | 11.42 / 6.70 s | 1.19 / 1.22 s | Yes / Yes |

Raw directories: `2026-11-04-v010-reuse-headless-4floors`, `...-8floors`, `...-8floors-02`. Another four-floor run with the browser renderer active took 2.13/4.17 s (`reuse-final-4floors`). This is a live desktop, not an isolated benchmark host; a process check during the variable eight-floor run found significant browser/UI and system-indexer CPU activity. This does not explain away the slower measurement: it is retained and reported. No stable p95 or cross-version whole-episode speedup is claimed.

Before the explicit reuse-bonus addition, the same constraint generator reached the same counts in 1.09/2.53 s at four floors and 2.68/7.09 s at eight floors (`bounded-final-*`). Later code changes add the reuse term, consistent realized reward reporting, accurate dictionary-use metadata and a cache bound. They do not alter the first untrained layout or its compatible proposal rules. Source snapshots distinguish these revisions.

The browser check (before the reward-only addition) displayed **7063 ms effective cycle / 7045 ms server episode**, eight floors, 606 policy decisions, 15 realized module types and one weight update; independent preview was valid. [Screenshot](../media/v010-bounded-browser.jpg). Preview occurred on Pause; the training cycle excluded realization. This is one interactive smoke case, not a latency distribution.

For a workload-matched component comparison, both old and new samplers received identical saved 480-node graphs (120 per floor × four), the same boundaries and an eight-proposal return budget per floor, seven repetitions. Old source is pinned to `3e9ed018`. Median four-floor sampling times were L: 60.65 → 3.61 ms; XL: 79.96 → 3.01 ms. Candidate sets can differ because new proposal work is bounded. The approximately 16.8×/26.6× ratios apply only to this component, not whole episodes or learned quality. See `2026-11-04-v010-sampler-matched/results.json`.

Instrumented before/after profiles use different reached graph sizes and cannot support a matched speedup ratio. Development timing directories are retained separately, including `bounded-dictionary-first`, whose manifest explicitly records an incomplete source snapshot.

## Correctness failures retained

An early four-floor XL development run produced two actual overlaps. Inspection found a support-interval bug: rounded normals were assumed to be exactly unit length. With nearly parallel observations, projection could incorrectly mark a required inequality redundant, prune it and expand a shared prototype. The fix normalizes each actual equation before projection and keeps the same explicit prior half-spaces as the polygon adapter. No tolerance was loosened to hide the overlaps. The exact near-parallel evidence is a regression fixture, and the failed audit remains in `2026-11-04-v010-bounded-dictionary-4floors`.

A sampler replay also exposed iteration-order dependence from unsorted neighbor-ID sets; offsets are now sorted before deterministic sampling. A serialization failure while saving site metadata interrupted the first ANY/FREE audit; the partial result and reason remain in `bounded-site-audit`. The corrected six-seed audit is `bounded-site-audit-02`.

All six ANY/FREE smoke layouts (seeds 17, 83, 251, 619, 1013, 2003; four floors; 120 max/floor) passed independent geometry validation. They reached only 30–141 floor instances at fill approximately 35–75%, all using 15 types. These small reached arrangements are not speed benchmarks, held-out quality evidence or proof of generalization. They expose the remaining compatible-growth limitation.

The full suite passes **279 tests, two skipped**. New regressions cover oblique area agreement with the polygon adapter, near-parallel pruning, required-contact loss, incompatible connections at the ceiling, rotated reuse, full-height identity, polygon-free probe/commit, independent reuse reward, no hole/vertical-copy credit, matching preview reward, bounded WebSocket batches and no benefit from delaying the same terminal failure. Both the working frontend and a clean release frontend excluding unrelated local UI changes build successfully. The final live WebSocket check completed one real update in 11 bursts, with 15 types, an 18.58-point independent reuse bonus and no realization (see `release-checks/websocket.json`; this concurrent functional check is not timing evidence).

## Remaining work

Better compatible growth, assignment/pose backtracking and alternative complete layouts matter as much as faster steps. Hard rejection at 15 types is not a substitute for learning good placement choices. No policy quality improvement, architecture winner, environmental calibration, general geometric feasibility, or superiority over the old collision-based generator has been demonstrated. The later quality protocol must use ANY/FREE with auto-changing sites, multiple training seeds, frozen held-out evaluation, independent geometry audits and retained failed runs.

Pre-commit governance: active branch verified as `version/v0.10.0`. No remote tracking ref exists for this branch; the release diff was inspected against `origin/main`. Core stacking tests remain present. Staged deletions are limited to superseded generated JS assets. Unrelated README, site-data and frontend edits remain unstaged. No push performed.

Final browser verification also caught stale library wording: live constraint-checked types were still described as provisional and an empty polygon list displayed zero shapes. The library now counts actual module IDs and labels them shared implicit types until preview, without constructing polygons during training. Both frontend builds passed again.

Final browser fixes: graph WebSocket replies now dispatch the next live graph step directly instead of passing through a zero-delay timer, which browsers can throttle in background tabs. Preview now aggregates the same per-floor objective as training rather than the legacy polygon score; its reuse bonus and total are covered by the preview-isolation regression. These changes do not feed realized scores into training.
